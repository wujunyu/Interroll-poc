# unit

骨架期为空。B 批补：

- `test_batch_flush.py`：满 200 行/1s 触发；
- `test_idempotent_upsert.py`：同 `(drive, ts, seq)` 重放不增行；
- `test_watermark.py`：水位线推进与回退检测。
