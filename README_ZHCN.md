# CloudCensorFxxkerWithFloppy

---

## 特性

只需将您的单个文件或文件夹转换为多个 IMG 软盘镜像文件，以规避百度网盘、夸克等云盘的审查。

请记住，您可以随后将这些 IMG 软盘镜像文件压缩成一个 ZIP / 7Z 文件，以便于传输和存储。

---

## 快速入门

1. 前往 [GitHub Release](https://github.com/scilxurkel001/CloudCensorFxxkerWithFloppy/releases) 并下载最新版本。
2. 前往 [Keygen Page](https://github.com/scilxurkel001/sxk-soft-keygen) 并下载注册机（keygen）。
3. 解压 ZIP 文件，你会看到 "CCFWF-Compressor" 和 "CCFWF-Extractor"。
4. 这两个工具都带有图形用户界面（GUI）及其独立的依赖项，因此不需要安装 Python 或使用命令行。而且这些工具不支持命令行操作方式。
5. 如果是首次运行，你需要对其进行激活，只需将你的机器码复制到注册机中，即可为其生成密钥。

压缩：
1. 运行 “CCFWF-Compressor”。
2. 选择源文件、软盘格式类型和输出字典。
3. 点击 “Start Matrix Compression and Generate Floppy Images”。
4. 耐心等待，完成后您将看到一个装满 IMG 文件的文件夹。

解压：
1. 运行 “CCFWF-Extractor”。
2. 选择包含软盘镜像的目录以及用于提取和合并的目标目录。
3. 点击 “Start Automatic Extraction and Merging”。
4. 耐心等待，完成后您将看到原始文件或文件夹。

## 🛠️ 建筑与安装

你需要：
- Python 3.8（这是为了兼容 Windows 7）
- Windows 7/10/11（推荐使用 Windows 10 或 11）

**强烈建议使用 [uv](https://github.com/astral-sh/uv) 进行高效的依赖管理。**

### 编译方法 1（强烈推荐）

如果您已安装 `uv`，请直接执行 `uv sync --python 3.8` 命令，待安装完成后进行下一步。

### 编译方法 2（传统方式）

如果您没有安装 `uv`，请确保您的 Python 版本为 3.8 或更高版本，然后按照以下步骤操作...

首先，执行命令 `python -m venv .venv` 来创建虚拟环境。
然后，执行命令 `.venv\Scripts\activate` (Windows) 或 `source .venv/bin/activate` (macOS / Linux) 来激活该环境。

最后，执行命令 `pip install -r requirements.txt` 来安装依赖项。
如果安装成功完成，您可以进行下一步。如果在安装过程中发生错误，请删除虚拟环境并重试，或者使用 `uv` 以获得更顺畅的安装体验。

## 调试与运行

在文件根目录下执行 `uv run <PYTHON_FILE>`。

或者，执行命令 `.venv\Scripts\activate`（Windows）或 `source .venv/bin/activate`（macOS / Linux）来激活环境，然后执行 `python <PYTHON_FILE>`。

## 发行打包

执行 `uv run pyinstaller -F --noconsole --name "CCFWF-Compressor" floppyCompress.py` / `uv run pyinstaller -F --noconsole --name "CCFWF-Extractor" floppyExtract.py`。

或者执行命令 `.venv\Scripts\activate` (Windows) 或 `source .venv/bin/activate` (macOS / Linux) 以激活环境，然后执行 `pyinstaller -F --noconsole --name "CCFWF-Compressor" floppyCompress.py` / `pyinstaller -F --noconsole --name "CCFWF-Extractor" floppyExtract.py`。

如果您使用的是 Qt 版本，则需要执行 `uv run pyinstaller -F --noconsole --name "CCFWF-Compressor-Qt" --add-data "fonts;fonts" floppyCompress-Qt.py` / `uv run pyinstaller -F --noconsole --name "CCFWF-Extractor-Qt" --add-data "fonts;fonts" floppyExtract-Qt.py`。

---

## 注意

- 由于使用了 PyInstaller，本程序生成的 EXE 文件可能会被各种杀毒软件立即检测并隔离。
- 最多可以生成 99,999 个文件；超过此限制可能会导致程序错误或不可预知的行为。根据提供的选项，1440KB 的设置支持的最大文件大小约为 137.3 GB。
- 虽然最多可以生成 99,999 个文件，但当加载过多小文件时（大约 10,000 个？），您的文件资源管理器将会崩溃，因此建议遵循下拉菜单中的提示。
- 为了避免在网盘中上传大量小文件导致的账号风控，请始终记得您可以为这些小的 IMG 文件创建压缩包。推荐使用 ISO 镜像，因为它无需解压即可挂载，这可以节省临时存储空间并延长硬盘寿命。可以使用 WinCDEmu（推荐 - 免费且开源）或 UltraISO（面向高级用户，需要付费密钥）来创建 ISO 文件。
- 若要清除激活状态：删除 "C:\Users\<用户名>\AppData\Roaming\CloudCensorFxxker" 文件夹。

## 许可协议
AGPL 许可证 - 欢迎随意分叉和研究，但你必须开源所有内容。这是为了防止网盘提供商使用它。

## 灵感来源
“夸克网盘清理电影资源”事件
