import random

from engine.models import Question

SAMPLE_QUESTIONS: list[Question] = [
    Question("What is the capital of Japan?", ["Osaka", "Tokyo", "Kyoto", "Nagoya"], 1),
    Question("Which planet is closest to the Sun?", ["Venus", "Mercury", "Mars", "Earth"], 1),
    Question("How many continents are there?", ["5", "6", "7", "8"], 2),
    Question("What is 12 x 12?", ["124", "144", "132", "154"], 1),
    Question("Which ocean is the largest?", ["Atlantic", "Indian", "Arctic", "Pacific"], 3),
    Question("What language is spoken in Brazil?", ["Spanish", "Portuguese", "French", "Italian"], 1),
    Question("How many sides does a hexagon have?", ["5", "6", "7", "8"], 1),
    Question("What is the chemical symbol for gold?", ["Go", "Gd", "Au", "Ag"], 2),
    Question("Which is the longest river?", ["Amazon", "Nile", "Yangtze", "Danube"], 1),
    Question("What year did the first Moon landing happen?", ["1965", "1969", "1972", "1958"], 1),
]


def pick_questions(count: int) -> list[Question]:
    count = min(count, len(SAMPLE_QUESTIONS))
    return random.sample(SAMPLE_QUESTIONS, count)