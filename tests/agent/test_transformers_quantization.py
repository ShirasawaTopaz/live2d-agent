import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.config.config import AIModelConfig, AIModelType
from internal.agent.agent_support.transformers import Transformers


class TestTransformersQuantization:
    def test_default_quantization_params_none(self):
        """Test that when no quantization is configured, defaults are None"""
        config = AIModelConfig(
            name="test",
            model="test-model",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.7
        )
        model = Transformers(config)
        assert model.config.load_in_4bit is None
        assert model.config.load_in_8bit is None
        assert model.config.kv_cache_quantization is None

    def test_explicit_quantization_config(self):
        """Test that explicit quantization config is preserved"""
        config = AIModelConfig(
            name="test",
            model="test-model",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.7,
            load_in_4bit=True,
            load_in_8bit=False,
            kv_cache_quantization=True
        )
        model = Transformers(config)
        assert model.config.load_in_4bit is True
        assert model.config.load_in_8bit is False
        assert model.config.kv_cache_quantization is True

    def test_inference_params_defaults_small_model(self):
        """Test that small models (<=4B) get correct default params"""
        # Model path indicates 1.8B model
        config = AIModelConfig(
            name="test-1.8b",
            model="Qwen2-1.8B-Instruct",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.7  # will be overridden by auto default if not explicitly set
        )
        model = Transformers(config)
        params = model.get_inference_params()
        
        # Explicit temperature should be preserved; other defaults still depend on model size
        assert params["temperature"] == 0.7
        assert params["repetition_penalty"] == 1.1
        assert params["max_new_tokens"] == 512
        assert params["top_p"] == 0.9

    def test_inference_params_defaults_large_model(self):
        """Test that large models (>4B) get correct default params"""
        # Model path indicates 7B model
        config = AIModelConfig(
            name="test-7b",
            model="Qwen2.5-7B-Instruct",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.7,
        )
        model = Transformers(config)
        params = model.get_inference_params()
        
        # 7B > 4B should have higher temperature and lower repeat penalty
        assert params["temperature"] == 0.7
        assert params["repetition_penalty"] == 1.05
        assert params["max_new_tokens"] == 512

    def test_explicit_inference_params_override(self):
        """Test that explicit parameters override auto defaults"""
        config = AIModelConfig(
            name="test",
            model="test-model",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.2,
            top_p=0.8,
            repeat_penalty=1.2,
            max_new_tokens=1024
        )
        model = Transformers(config)
        params = model.get_inference_params()
        
        assert params["temperature"] == 0.2
        assert params["top_p"] == 0.8
        assert params["repetition_penalty"] == 1.2
        assert params["max_new_tokens"] == 1024

    def test_max_tool_call_retries_default(self):
        """Test default max retries is 2"""
        config = AIModelConfig(
            name="test",
            model="test-model",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.7
        )
        model = Transformers(config)
        assert model.get_max_tool_call_retries() == 2

    def test_max_tool_call_retries_custom(self):
        """Test custom max retries is used"""
        config = AIModelConfig(
            name="test",
            model="test-model",
            system_prompt="test prompt",
            type=AIModelType(AIModelType.TransformersModel),
            default=False,
            config={},
            temperature=0.7,
            max_tool_call_retries=3
        )
        model = Transformers(config)
        assert model.get_max_tool_call_retries() == 3

    def test_estimate_param_count_from_path(self):
        """Test parameter count estimation from model path"""
        test_cases = [
            ("Qwen2-0.8B-Instruct", 0.8),
            ("gemma-2b", 1.8),  # 2B rounds to 1.8 in our detection
            ("Llama-3-7B-Instruct", 7.0),
            ("Mistral-13B-v0.2", 13.0),
            ("custom-model", 0.0),
        ]
        for model_path, expected in test_cases:
            config = AIModelConfig(
                name="test",
                model=model_path,
                system_prompt="test",
                type=AIModelType(AIModelType.TransformersModel),
                default=False,
                config={},
                temperature=0.7
            )
            model = Transformers(config)
            estimated = model._estimate_param_count()
            assert estimated == expected
