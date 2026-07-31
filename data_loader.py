import json
from pathlib import Path


# 현재 프로젝트 폴더 위치
BASE_DIR = Path(__file__).resolve().parent

# data 폴더 위치
DATA_DIR = BASE_DIR / "data"


def load_json(file_name):
    """
    data 폴더에 있는 JSON 파일을 읽어서 반환합니다.
    """

    file_path = DATA_DIR / file_name

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        raise FileNotFoundError(
            f"{file_name} 파일을 찾을 수 없습니다. "
            f"data 폴더 안에 파일이 있는지 확인해주세요."
        )

    except json.JSONDecodeError as error:
        raise ValueError(
            f"{file_name}의 JSON 형식이 올바르지 않습니다. "
            f"{error.lineno}번째 줄을 확인해주세요."
        )


# 각 JSON 파일 불러오기
CHARACTERS = load_json("characters.json")
FOODS = load_json("foods.json")
ANSWER_PATTERNS = load_json("answer_patterns.json")
