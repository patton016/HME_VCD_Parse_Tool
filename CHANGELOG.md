# Changelog

All notable changes to the HME VCD Parse Tool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-09-19

### Added
- 初始版本发布，核心脚本 `parse_debugware_vcd.py`。
- 支持 `--start` 与 `--end` 组合筛选时间范围。
- 支持 `--addr` 与 `--context` 组合筛选地址上下文。
- 支持生成 `--csv` 输出文件，并可通过 `--output` 指定输出路径。

### Verified
- 已在 Win10 x64 环境下完成人工测试核验，覆盖上述参数组合与输出格式。
