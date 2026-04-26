import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internal.agent.bubble_timing import BubbleTimingController, calculate_bubble_duration


def test_calculate_bubble_duration_applies_minimum_weighting_and_maximum():
    assert calculate_bubble_duration("") == 5000
    assert calculate_bubble_duration("hello") == 5000
    assert calculate_bubble_duration("中" * 40) > calculate_bubble_duration("a" * 40)
    assert calculate_bubble_duration("a" * 1000) == 30000


def test_wait_for_bubble_interval_uses_previous_bubble_end_time():
    controller = BubbleTimingController(time_provider=lambda: 12.0)
    controller.last_bubble_time = 10.0
    controller.last_bubble_duration = 5000

    assert abs(controller.wait_for_bubble_interval(5000) - 3.0) < 1e-9


async def _run_send_single_bubble_parses_json_and_updates_state():
    sent_payloads = []

    async def fake_sender(_ws, _msg, _msg_id, data):
        sent_payloads.append(data)

    controller = BubbleTimingController(
        time_provider=lambda: 42.0,
        sender=fake_sender,
    )

    await controller.send_single_bubble(
        '{"data":{"id":7,"text":"Hello world","textColor":12345}}',
        object(),
        None,
    )

    assert len(sent_payloads) == 2
    expression_payload = sent_payloads[0]
    assert expression_payload.id == 7

    payload = sent_payloads[1]
    assert payload.id == 7
    assert payload.text == "Hello world"
    assert payload.textColor == 12345
    assert payload.duration == 5000
    assert controller.last_bubble_time == 42.0
    assert controller.last_bubble_duration == 5000


def test_send_single_bubble_parses_json_and_updates_state():
    asyncio.run(_run_send_single_bubble_parses_json_and_updates_state())


async def _run_send_stream_chunk_rotates_expression_once_per_bubble():
    sent_payloads = []

    async def fake_sender(_ws, _msg, _msg_id, data):
        sent_payloads.append(data)

    controller = BubbleTimingController(sender=fake_sender)

    await controller.send_stream_chunk(
        "Hello",
        5000,
        object(),
        None,
        first_chunk=True,
    )
    await controller.send_stream_chunk(
        "Hello world",
        5000,
        object(),
        None,
        first_chunk=False,
    )

    assert len(sent_payloads) == 3
    assert sent_payloads[0].id == 0
    assert sent_payloads[1].text == "Hello"
    assert sent_payloads[2].text == "Hello world"


def test_send_stream_chunk_rotates_expression_once_per_bubble():
    asyncio.run(_run_send_stream_chunk_rotates_expression_once_per_bubble())
