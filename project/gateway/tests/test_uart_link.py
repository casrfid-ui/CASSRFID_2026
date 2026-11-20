import struct
from ffn_gateway import uart_link as U


def test_crc_check_value():
    assert U.crc16(b"123456789") == 0x29B1


def test_roundtrip_with_escapes():
    d = U.Decoder()
    pl = bytes([0x7E, 0x7D, 0x00, 0x20, 0x5E])
    msgs = d.feed(U.encode(0x81, pl))
    assert len(msgs) == 1 and msgs[0].type == 0x81 and msgs[0].data == pl


def test_bad_crc_dropped_and_resync():
    d = U.Decoder()
    w = bytearray(U.encode(0x01, b"abc"))
    w[3] ^= 0xFF
    out = d.feed(bytes(w) + U.encode(0x02, b"ok"))
    assert [m.type for m in out] == [0x02] and d.bad_crc == 1


def test_parse_messages():
    rx = U.parse(U.Msg(U.BR_RX_FRAME, struct.pack("bb", -97, 30) + bytes(16)))
    assert rx.rssi == -97 and rx.snr == 30 and len(rx.wire) == 16
    st = U.parse(U.Msg(U.BR_STATUS, struct.pack(">IBBBHHH", 100, 0b1011, 3, 18, 7, 6, 1)))
    assert st.sbc_up and st.modem_ready and not st.alert_armed and st.have_time and st.csq == 18 and st.frames_rx == 7
    assert U.parse(U.Msg(U.BR_EMERGENCY, bytes([1, 1, 2]))).n_numbers == 2
    assert U.parse(U.Msg(U.BR_SMS_RESULT, bytes([5, 0x80, 0]))).id == 0x8005


def test_sms_message_layout():
    d = U.Decoder()
    m = d.feed(U.send_sms(3, "+216123", "hello"))[0]
    assert m.type == U.SB_SEND_SMS and m.data[0] == 3 and m.data[2] == 7 and m.data[3:10] == b"+216123" and m.data[10:] == b"hello"


def test_memory_link_pipeline():
    ml = U.MemoryLink()
    link = U.Link(ml)
    ml.inject(U.BR_EMERGENCY, bytes([2, 4, 1]))
    link.pump(ml.read())
    assert link.inbox.get_nowait().box == 2
    link.send(U.ping())
    assert ml.take_sent()[0].type == U.SB_PING
