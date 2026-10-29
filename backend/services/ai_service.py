from backend.models.change_plan import ChangePlan


class AIService:

    def parse_change_request(
        self,
        user_request: str,
        drawing_context: dict
    ) -> ChangePlan:

        raise NotImplementedError