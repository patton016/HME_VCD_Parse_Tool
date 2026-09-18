# HME VCD Waveform Parsing Toolkit

本工具可用于将 京微齐力 HME FPGA 的 Debugware VCD 波形文件按字段解析导出为可读的文本表格或 CSV格式。
只要提供与 VCD 信号位宽一致的 Verilog 拼接布局文件，即可支持 160/180/280/360/400/420/576/640 等任意 debugware 宽度。

---

## 目录结构

```
HME_VCD_Parse_Tool/
├── parse_debugware_vcd.py       # 主解析脚本（不依赖特定工程路径）
├── debug_data_layout.txt        # 示例：420-bit debug_data 的 Verilog 拼接定义
├── python_installer/            # Python 安装包（新用户先安装）
│   └── python-3.10.9-amd64.exe
├── example/
│   └── debugware_420_example.vcd# 一段真实波形示例（420-bit）
├── result/
│   └── debugware_80-100.csv     # 示例 CSV 输出
└── README.md                    # 本说明
```

软件脚本建议解压至 HME FPGA 工程的 debug 目录下运行。
---

## 环境要求

- **Python 3.7 或更高版本**（脚本仅使用标准库：`sys`、`re`、`argparse`、`collections`）
- 无额外第三方依赖

如果当前机器没有 Python，请先安装：

```
HME_VCD_Parse_Tool/python_installer/python-3.10.9-amd64.exe
```

安装时建议勾选 **"Add Python to PATH"**，安装完成后在命令行输入 `python --version` 验证。

---

## 使用说明

### 1. 把示例 VCD 导出为 CSV（420-bit）

```bash
cd HME_VCD_Parse_Tool
python parse_debugware_vcd.py ./example/debugware_420_example.vcd \
    --signal data_in_0 \
    --layout debug_data_layout.txt \
    --start 80000 --end 100000 \
    --csv --output ./result/debugware_80-100.csv
```

`--start` 和 `--end` 的时间单位由 VCD 文件中的 `$timescale` 决定。

### 2. 解析实际上板抓到的 VCD

例如当前目录下已有 `debugware_420_0.vcd`，且信号名为 `data_in_0[419:0]`：

```bash
python parse_debugware_vcd.py debugware_420_0.vcd \
    --layout debug_data_layout.txt \
    --addr 0x0684 --context 5
```

默认信号名为 `data_in_0`，支持带位宽后缀的写法。如果你的 VCD 中信号名不同（例如 `debug_data`），用 `--signal` 指定 leaf 名或完整层次名。

### 3. 解析其它宽度的 debugware

假设有一个 640-bit 的 VCD，并配有对应的 `debug_data_layout_640.txt`：

```bash
python parse_debugware_vcd.py debugware_640_0.vcd \
    --layout debug_data_layout_640.txt \
    --addr 0x19a5 --context 3 \
    --output dump_19a5.txt
```

脚本会自动识别 VCD 中信号的位宽，并与 `--layout` 文件的总位宽做校验；不匹配时会提示需要哪种宽度的布局文件。

### 4. 只输出指定字段

```bash
python parse_debugware_vcd.py debugware_420_0.vcd \
    --layout debug_data_layout.txt \
    --fields time,cpu_haddr,cpu_addr_reg,cpu_hrdata,state,hit \
    --csv --output dump.csv
```

---

## 命令行参数

| 参数 | 说明 |
|------|------|
| `vcd` | 输入 VCD 文件路径 |
| `--signal`, `-s` | `debug_data` 信号名或完整层次名（默认 `data_in_0`，位宽后缀如 `[419:0]` 会自动忽略） |
| `--layout`, `-l` | 字段布局文件（含 `assign debug_data = {...};`） |
| `--start`, `-t0` | 起始时间，如 `100ns` 或 `100` |
| `--end`, `-t1` | 结束时间 |
| `--addr`, `-a` | 仅输出 `cpu_haddr` 等于该地址的采样行 |
| `--context`, `-c` | 配合 `--addr`，输出匹配行前后 N 行 |
| `--fields`, `-f` | 仅输出指定字段，逗号分隔 |
| `--csv` | 输出 CSV 格式 |
| `--output`, `-o` | 输出文件路径（默认 stdout） |

---

## 关于字段布局

`debug_data_layout.txt` 必须包含一个形如下面的 Verilog 拼接块：

```verilog
assign debug_data = {
    data_fwd_word_addr[29:0], data_fwd_data[31:0], ...
};
```

脚本会按逗号拆分每一项，自动识别：
- 常量：`13'b0`
- 信号切片：`data_fwd_word_addr[29:0]`
- 单比特信号：`cpu_hwrite`

字段顺序对应 VCD 中的 **MSB -> LSB**。总位宽会自动计算，并与 VCD 信号位宽校验。

---

## 示例输出

`result/debugware_80-100.csv` 是用第 1 节命令从 `example/debugware_420_example.vcd` 的 `80000 ~ 100000` 时间区间导出的 CSV 示例，包含该时间段内各字段的采样值。

---

## 注意事项

- **脚本不依赖任何特定工程路径**，只通过命令行参数读取 VCD 和布局文件。
- 省略 `--layout` 时，脚本会回退到内置的 420-bit 默认布局；如果 VCD 信号不是 420-bit，会报错并提示提供匹配的布局文件。
- 脚本输出的 `time` 列以 VCD 的 `$timescale` 为单位。

## 技术信息
- 开发者: 刘敏
- 微信公众号: 老刘记事儿
- 网站: www.fpga.pw
- 版本: V1.0.0

## 免责声明
-------------
本软件工具为个人非盈利性开源作品，请谨慎评估使用，如造成商业损失，发布者概不负责。