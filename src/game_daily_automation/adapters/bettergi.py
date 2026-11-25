"""BetterGI adapter; invocation details are configured only after local verification."""

from game_daily_automation.adapters.base import ConfiguredGameAdapter, ResultClassifier
from game_daily_automation.config.loader import GameToolConfig
from game_daily_automation.domain.enums import GameKey
from game_daily_automation.infrastructure.process_runner import ProcessRunner


class BetterGIAdapter(ConfiguredGameAdapter):
    def __init__(
        self,
        config: GameToolConfig,
        process_runner: ProcessRunner | None = None,
        result_classifier: ResultClassifier | None = None,
    ) -> None:
        super().__init__(GameKey.BETTERGI, config, process_runner, result_classifier)
