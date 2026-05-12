from typing import Any, Generator
from core.ai_model.base.ai_model_base import AIModelBase

class AIModelOnlineBase(AIModelBase):
    def __init__(self, config: Any, helper: Any):
        super().__init__(config, helper)
        self.mode = "online"

    def chat_stream(self, signal: Any, data: Any) -> Generator[Any, None, None]:
        def _generate() -> Generator[Any, None, None]:
            try:
                yield from self.stream_generator_framework(signal, data)
            except Exception as ex:
                error_msg = str(ex)
                print(f"Error: {error_msg}")
        return _generate