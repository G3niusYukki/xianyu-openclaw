from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.startup_checks import _is_production_env, check_quote_mock_guard


class TestIsProductionEnv:
    def test_env_prod(self):
        with patch.dict("os.environ", {"OPENCLAW_ENV": "production"}, clear=False):
            assert _is_production_env() is True

    def test_env_prod_short(self):
        with patch.dict("os.environ", {"APP_ENV": "prod"}, clear=False):
            assert _is_production_env() is True

    def test_config_runtime_pro(self):
        env_patch = {
            "OPENCLAW_ENV": "",
            "APP_ENV": "",
            "ENV": "",
            "PYTHON_ENV": "",
        }
        mock_config = MagicMock()
        mock_config.get.return_value = "pro"

        with patch.dict("os.environ", env_patch, clear=False):
            with patch("src.core.config.get_config", return_value=mock_config):
                assert _is_production_env() is True

    def test_config_exception_fallback(self):
        env_patch = {
            "OPENCLAW_ENV": "",
            "APP_ENV": "",
            "ENV": "",
            "PYTHON_ENV": "",
        }
        with patch.dict("os.environ", env_patch, clear=False):
            with patch("src.core.config.get_config", side_effect=RuntimeError):
                with patch("src.core.startup_checks.resolve_runtime_mode", return_value="auto"):
                    assert _is_production_env() is False

    def test_resolve_runtime_mode_pro(self):
        env_patch = {
            "OPENCLAW_ENV": "",
            "APP_ENV": "",
            "ENV": "",
            "PYTHON_ENV": "",
        }
        with patch.dict("os.environ", env_patch, clear=False):
            with patch("src.core.config.get_config", side_effect=RuntimeError):
                with patch("src.core.startup_checks.resolve_runtime_mode", return_value="pro"):
                    assert _is_production_env() is True


class TestCheckQuoteMockGuard:
    def test_prod_allow_mock_critical(self):
        mock_config = MagicMock()
        mock_config.get_section.return_value = {
            "providers": {"remote": {"allow_mock": True}}
        }
        with patch("src.core.config.get_config", return_value=mock_config), \
             patch("src.core.startup_checks._is_production_env", return_value=True):
            result = check_quote_mock_guard()
            assert result.passed is False
            assert result.critical is True

    def test_nonprod_allow_mock_warning(self):
        mock_config = MagicMock()
        mock_config.get_section.return_value = {
            "providers": {"remote": {"allow_mock": True}}
        }
        with patch("src.core.config.get_config", return_value=mock_config), \
             patch("src.core.startup_checks._is_production_env", return_value=False):
            result = check_quote_mock_guard()
            assert result.passed is False
            assert result.critical is False

    def test_prod_mock_disabled(self):
        mock_config = MagicMock()
        mock_config.get_section.return_value = {
            "providers": {"remote": {"allow_mock": False}}
        }
        with patch("src.core.config.get_config", return_value=mock_config), \
             patch("src.core.startup_checks._is_production_env", return_value=True):
            result = check_quote_mock_guard()
            assert result.passed is True
            assert result.critical is True

    def test_nonprod_mock_disabled(self):
        mock_config = MagicMock()
        mock_config.get_section.return_value = {
            "providers": {"remote": {"allow_mock": False}}
        }
        with patch("src.core.config.get_config", return_value=mock_config), \
             patch("src.core.startup_checks._is_production_env", return_value=False):
            result = check_quote_mock_guard()
            assert result.passed is True
            assert result.critical is False

    def test_exception_handling(self):
        with patch("src.core.config.get_config", side_effect=RuntimeError("fail")):
            result = check_quote_mock_guard()
            assert result.passed is False
            assert result.critical is True
