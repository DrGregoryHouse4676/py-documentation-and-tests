from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from cinema.models import Movie, Genre, Actor
from cinema.serializers import MovieListSerializer, MovieDetailSerializer


MOVIE_URL = reverse("cinema:movie-list")

_TOKEN_CACHE = {}


def sample_movie(**params):
    defaults = {"title": "Test movie", "description": "Some description", "duration": 120}
    defaults.update(params)
    return Movie.objects.create(**defaults)


def sample_genre(name="Action"):
    return Genre.objects.create(name=name)


def sample_actor(first_name="John", last_name="Doe"):
    return Actor.objects.create(first_name=first_name, last_name=last_name)


def auth_client(email: str, password: str) -> APIClient:
    client = APIClient()
    token = _TOKEN_CACHE.get(email)
    if not token:
        res = client.post(
            reverse("user:token_obtain_pair"),
            {"email": email, "password": password},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK, res.data
        token = res.data["access"]
        _TOKEN_CACHE[email] = token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class UnauthenticateMovieApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required_for_list(self):
        res = self.client.get(MOVIE_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticateMovieApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="test@example.com", password="password123"
        )
        self.admin = get_user_model().objects.create_superuser(
            email="admin.user@cinema.com", password="1qazcde3"
        )
        self.authed_client = auth_client("test@example.com", "password123")

    def _payload_list(self, data):
        return data["results"] if isinstance(data, dict) and "results" in data else data

    def test_jwt_obtain_and_list(self):
        res = self.authed_client.get(MOVIE_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_movie_list_matches_serializer(self):
        sample_movie(title="M1")
        sample_movie(title="M2")
        movies = Movie.objects.all().prefetch_related("genres", "actors").order_by("id")
        serializer = MovieListSerializer(movies, many=True)
        res = self.authed_client.get(MOVIE_URL)
        payload = self._payload_list(res.data)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual([m["id"] for m in payload], [m.id for m in movies])
        self.assertEqual([m["title"] for m in payload], [m.title for m in movies])

    def test_retrieve_movie(self):
        movie = sample_movie()
        movie.genres.add(sample_genre())
        movie.actors.add(sample_actor())
        url = reverse("cinema:movie-detail", args=[movie.id])
        res = self.authed_client.get(url)
        serializer = MovieDetailSerializer(movie)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_filter_by_title_partial_and_case_insensitive(self):
        sample_movie(title="Inception")
        sample_movie(title="Star Wars")
        res1 = self.authed_client.get(MOVIE_URL, {"title": "incep"})
        res2 = self.authed_client.get(MOVIE_URL, {"title": "INCEPTION"})
        titles1 = [m["title"] for m in self._payload_list(res1.data)]
        titles2 = [m["title"] for m in self._payload_list(res2.data)]
        self.assertIn("Inception", titles1)
        self.assertIn("Inception", titles2)
        self.assertNotIn("Star Wars", titles1)

    def test_filter_by_genres_csv_all_semantics(self):
        g1 = sample_genre("Action")
        g2 = sample_genre("Sci-Fi")
        g3 = sample_genre("Drama")
        m1 = sample_movie(title="Inception")
        m2 = sample_movie(title="Matrix")
        m3 = sample_movie(title="La La Land")
        m1.genres.add(g1, g2)
        m2.genres.add(g1)
        m3.genres.add(g3)
        res = self.authed_client.get(MOVIE_URL, {"genres": f"{g1.id},{g2.id}"})
        titles = [m["title"] for m in self._payload_list(res.data)]
        self.assertIn("Inception", titles)
        self.assertNotIn("Matrix", titles)
        self.assertNotIn("La La Land", titles)

    def test_filter_by_actors_csv_all_semantics(self):
        a1 = sample_actor("Keanu", "Reeves")
        a2 = sample_actor("Carrie-Anne", "Moss")
        m1 = sample_movie(title="The Matrix")
        m2 = sample_movie(title="John Wick")
        m1.actors.add(a1, a2)
        m2.actors.add(a1)
        res = self.authed_client.get(MOVIE_URL, {"actors": f"{a1.id},{a2.id}"})
        titles = [m["title"] for m in self._payload_list(res.data)]
        self.assertIn("The Matrix", titles)
        self.assertNotIn("John Wick", titles)


class MovieAdminActionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="user@example.com", password="password123"
        )
        self.admin = get_user_model().objects.create_superuser(
            email="admin.user@cinema.com", password="1qazcde3"
        )
        self.user_client = auth_client("user@example.com", "password123")
        self.admin_client = auth_client("admin.user@cinema.com", "1qazcde3")

    def test_create_forbidden_for_non_admin(self):
        g = sample_genre("Thriller")
        a = sample_actor("Keanu", "Reeves")
        payload = {
            "title": "Speed",
            "description": "Bus bomb thriller",
            "duration": 116,
            "genres": [g.id],
            "actors": [a.id],
        }
        res = self.user_client.post(MOVIE_URL, payload, format="json")
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_admin_can_create(self):
        g = sample_genre("Mystery")
        a = sample_actor("Rachel", "Weisz")
        payload = {
            "title": "Constantine",
            "description": "Occult",
            "duration": 121,
            "genres": [g.id],
            "actors": [a.id],
        }
        res = self.admin_client.post(MOVIE_URL, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        movie_id = res.data["id"]
        self.assertTrue(Movie.objects.filter(id=movie_id).exists())
