"""March7th adapter; task IDs and result signals require local verification."""

from game_daily_automation.adapters.base import ConfiguredGameAdapter, ResultClassifier
from game_daily_automation.config.loader import GameToolConfig
from game_daily_automation.domain.enums import GameKey
from game_daily_automation.infrastructure.process_runner import ProcessRunner


class March7thAdapter(ConfiguredGameAdapter):
    def __init__(
        self,
        config: GameToolConfig,
        process_runner: ProcessRunner | None = None,
        result_classifier: ResultClassifier | None = None,
    ) -> None:
        super().__init__(GameKey.MARCH7TH, config, process_runner, result_classifier)
