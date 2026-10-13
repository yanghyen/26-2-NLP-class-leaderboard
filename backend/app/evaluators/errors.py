"""Fixed public messages; never echo keys, paths, manifests or exception details."""

SAFE_EVALUATOR_MESSAGES = {
    "EVALUATOR_NOT_AVAILABLE": "아직 사용할 수 없는 evaluator입니다.",
    "UNKNOWN_EVALUATOR": "알 수 없는 evaluator 설정입니다.",
    "EVALUATOR_CONFIG_INVALID": "evaluator 설정이 올바르지 않습니다.",
    "LAB02_MANIFEST_INVALID": "Lab02 manifest 또는 파일 구성이 올바르지 않습니다.",
    "LAB02_CONFIG_INVALID": "Lab02 모델 config가 평가 규격과 일치하지 않습니다.",
}


class EvaluatorError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(SAFE_EVALUATOR_MESSAGES[code])
