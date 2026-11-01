import math

import pytest

from hardware_api.esp32_protocol import (
  ProtocolError,
  Reply,
  encode_drive,
  mps_to_rpm,
  parse_battery,
  parse_encoders,
  parse_reply,
)


def test_encode_drive_formats_two_decimals():
  assert encode_drive(12.345, -3.0) == b'D 12.35 -3.00\n'


def test_encode_drive_rejects_non_finite():
  with pytest.raises(ValueError):
    encode_drive(math.nan, 0.0)


def test_parse_reply_splits_kind_and_args():
  assert parse_reply(b'E 100 -20\r\n') == Reply('E', ('100', '-20'))
  assert parse_reply(b'OK D\n') == Reply('OK', ('D',))


@pytest.mark.parametrize('line', [b'', b'\n', b'HELLO\n', b'\xff\n'])
def test_parse_reply_rejects_junk_and_timeouts(line):
  with pytest.raises(ProtocolError):
    parse_reply(line)


def test_parse_encoders_and_battery():
  assert parse_encoders(Reply('E', ('8192', '-4096'))) == (8192, -4096)
  assert parse_battery(Reply('B', ('19.85',))) == pytest.approx(19.85)


def test_parse_encoders_rejects_wrong_shape():
  with pytest.raises(ProtocolError):
    parse_encoders(Reply('E', ('1',)))
  with pytest.raises(ProtocolError):
    parse_encoders(Reply('B', ('1', '2')))


def test_mps_to_rpm_one_turn_per_second():
  radius = 0.05
  assert mps_to_rpm(2.0 * math.pi * radius, radius) == pytest.approx(60.0)
