from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.reverse import reverse

from cinema.models import Movie, Genre, Actor
from cinema.serializers import MovieListSerializer, MovieDetailSerializer

from rest_framework.test import APIClient
from rest_framework import status


MOVIE_URL = reverse("cinema:movie-list")


def sample_movie(**params):
    defaults = {
        "title": "Test movie",
        "description": "Some description",
        "duration": 120,
    }
    defaults.update(params)
    return Movie.objects.create(**defaults)

def sample_genre(name="Action"):
    return Genre.objects.create(name=name)

def sample_actor(first_name="John", last_name="Doe"):
    return Actor.objects.create(first_name=first_name, last_name=last_name)


class UnauthenticateMovieApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        res = self.client.get(MOVIE_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticateMovieApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(email="test@example.com", password="<PASSWORD>")
        self.client.force_authenticate(self.user)
        res = self.client.get(MOVIE_URL)
        movies = Movie.objects.all().prefetch_related("genres", "actors")
        serializer = MovieListSerializer(movies, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_movie_filters_by_title(self):
        sample_movie(title="Inception")
        sample_movie(title="Star wars")
        res = self.client.get(MOVIE_URL, {"title": "Inception"})
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["title"], "Inception")

    def test_movie_filters_by_genres(self):
        genre1 = sample_genre(name="Action")
        genre2 = sample_genre(name="Science fiction")
        movie1 = sample_movie(title="Inception")
        movie2 = sample_movie(title="Star wars")
        movie1.genres.add(genre1)
        movie2.genres.add(genre2)
        res = self.client.get(MOVIE_URL, {"genres": f"{genre1.id}"})
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["title"], "Inception")

    def test_movie_filters_by_actors(self):
        movie1 = sample_movie(title="Inception")
        movie2 = sample_movie(title="Star wars")
        actor1 = sample_actor(first_name="Poul", last_name="Walker")
        actor2 = sample_actor(first_name="Jason", last_name="Statham")
        movie1.actors.add(actor1)
        movie2.actors.add(actor2)
        res = self.client.get(MOVIE_URL, {"actors": f"{actor1.id}"})
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["title"], "Inception")

    def test_retrieve_movie(self):
        movie = sample_movie()
        movie.genres.add(sample_genre())
        movie.actors.add(sample_actor())
        url = reverse("cinema:movie-detail", args=[movie.id])
        res = self.client.get(url)
        serializer = MovieDetailSerializer(movie)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

