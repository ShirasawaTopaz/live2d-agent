#!/usr/bin/env python3
"""Test that the fix for repetition_penalty vs repeat_penalty works"""

import logging
logging.basicConfig(level=logging.INFO)

from internal.config.config import AIModelConfig, AIModelType
from internal.agent.agent_support.transformers import Transformers

# Create a test config
config = AIModelConfig(
    name="test",
    model="Qwen3.5-0.8B",
    system_prompt="test prompt",
    type=AIModelType(AIModelType.TransformersModel),
    default=False,
    config={},
    temperature=0.7,
    repeat_penalty=1.2,
)

model = Transformers(config)
params = model.get_inference_params()

print(f"Generated inference params:")
print(params)

# Check that the key is correct
if 'repetition_penalty' in params:
    print(f"\n✅ SUCCESS: 'repetition_penalty' found in params")
    print(f"   Value: {params['repetition_penalty']}")
else:
    print(f"\n❌ FAIL: 'repetition_penalty' NOT found in params")
    
if 'repeat_penalty' in params:
    print(f"\n⚠️   WARNING: 'repeat_penalty' still found in params")
    
print(f"\nTest complete. Original error was that HF didn't recognize 'repeat_penalty' as a generate parameter.")
print(f"Now we pass 'repetition_penalty' which is what HF expects.")