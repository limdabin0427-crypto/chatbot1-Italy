from data_loader import ANSWER_PATTERNS


def get_answer_pattern(country):
    """
    나라별 답변 순서를 가져옵니다.

    예:
    ["yes", "no", "yes"]
    """

    pattern = ANSWER_PATTERNS.get(country)

    if not pattern:
        return ["yes", "no", "yes"]

    return pattern


def get_food_answer(country, question_number):
    """
    몇 번째 음식 질문인지에 따라 yes 또는 no를 반환합니다.

    question_number:
    0 = 첫 번째 질문
    1 = 두 번째 질문
    2 = 세 번째 질문
    """

    pattern = get_answer_pattern(country)

    if question_number < 0:
        question_number = 0

    if question_number >= len(pattern):
        return None

    return pattern[question_number]


def make_food_response(answer, food_name):
    """
    3학년 수준의 고정 문장으로 답변을 만듭니다.
    """

    if answer == "yes":
        return f"Yes, I do. I like {food_name}."

    if answer == "no":
        return f"No, I don't. I don't like {food_name}."

    return None
