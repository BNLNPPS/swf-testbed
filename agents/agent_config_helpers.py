import os
import tomllib


class PromptProcessingConfigMixin:
    """Shared prompt-processing config helpers for local testbed agents."""

    def _prompt_processing_config_path(self):
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows", "prompt_processing.toml")

    def _load_prompt_processing_section(self, config_path, warn=False):
        if not config_path:
            return {}
        try:
            with open(config_path, "rb") as config_file:
                return tomllib.load(config_file).get("prompt_processing", {})
        except (OSError, TypeError, tomllib.TOMLDecodeError) as e:
            if warn:
                self.logger.warning(
                    f"Could not load prompt_processing config from {config_path}: {e}",
                    extra=self._log_extra()
                )
            return {}

    def _load_prompt_processing_config(self):
        """Load prompt-processing settings, with workflow defaults plus active config overrides."""
        prompt_config = self._load_prompt_processing_section(self._prompt_processing_config_path(), warn=True)
        active_config = self._load_prompt_processing_section(self.config_path, warn=True)
        prompt_config.update(active_config)
        return prompt_config

    def _config_bool(self, config, key, env_var, default):
        """Read a boolean setting from config, with an environment override."""
        value = os.getenv(env_var, config.get(key, default))
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _config_int(self, config, key, env_var, default):
        """Read an integer setting from config, with an environment override."""
        value = os.getenv(env_var, config.get(key, default))
        try:
            return int(value)
        except (TypeError, ValueError):
            self.logger.warning(
                f"Invalid {key} value {value!r}; using default {default}",
                extra=self._log_extra()
            )
            return default

    def _config_list(self, config, key, env_var, default):
        """Read a comma-separated list setting from config, with an environment override."""
        value = os.getenv(env_var, config.get(key, default))
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return list(default)

    def _message_bool(self, message_data, key, default):
        value = message_data.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


class DecisionDatasetNamingMixin:
    """Shared decision-box message and dataset helpers."""

    def _decision_box_context_for_run(self, run_id):
        return {}

    def _decision_box_enabled_for_message(self, message_data, run_id=None):
        if "decision_box_enabled" in message_data:
            return self._message_bool(message_data, "decision_box_enabled", self.decision_box_enabled)
        if run_id is not None:
            context = self._decision_box_context_for_run(run_id)
            if "decision_box_enabled" in context:
                return bool(context["decision_box_enabled"])
        return self.decision_box_enabled

    def _non_decision_box_site_for_message(self, message_data, run_id=None):
        site = message_data.get("non_decision_box_site")
        if site:
            return str(site).strip()
        if run_id is not None:
            context = self._decision_box_context_for_run(run_id)
            site = context.get("non_decision_box_site")
            if site:
                return str(site).strip()
        return getattr(self, "non_decision_box_site", None)

    def _run_dataset_name(self, run_number=None):
        dataset = getattr(self, "dataset", None)
        if dataset:
            return dataset
        if run_number is not None:
            return f"swf.{run_number}.run"
        return ""

    def _run_dataset_did(self, run_number=None):
        return f"{self.decision_box_rucio_scope}:{self._run_dataset_name(run_number)}"

    def _input_dataset_name_for_site(self, run_number, site_name):
        run_dataset_name = f"swf.{run_number}.run"
        if self.decision_box_site_dataset_template:
            return self.decision_box_site_dataset_template.format(
                run_dataset_name=run_dataset_name,
                run_number=run_number,
                site_name=site_name,
                site=site_name,
            )
        return f"{self._run_dataset_name(run_number)}.{site_name}"

    def _input_dataset_did_for_site(self, run_number, site_name):
        return f"{self.decision_box_rucio_scope}:{self._input_dataset_name_for_site(run_number, site_name)}"

    def _site_name_for_dataset(self, run_number, dataset_did):
        for site_name in self.decision_box_sites:
            if dataset_did == self._input_dataset_did_for_site(run_number, site_name):
                return site_name
        return None
