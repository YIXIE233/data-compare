# data compare

CSV 来源对参考目录。映射在 sqlite，差异写到 `data/<模块>/<分类>/<需求>/diff.xlsx`。

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python run_server.py
```

http://127.0.0.1:8000

样本：`data/samples/sample.csv`（列 `name,value,period`）

自检：`python -m server.check`
