#!/usr/bin/env python3
"""
文档处理工具集 - PDF/Word/Excel/PPT 标准化接口
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import tool, registry

# ============================================
# PDF 工具 (基于 nano-pdf)
# ============================================

@tool("pdf_extract_text", "提取 PDF 文本", category="document", requires_confirmation=False)
def pdf_extract_text(file: str, pages=None):
    """提取 PDF 文件文本内容"""
    try:
        from nano_pdf import extract_text
        return {"text": extract_text(file, pages=pages)}
    except ImportError:
        raise RuntimeError("nano_pdf skill not installed")
    except Exception as e:
        raise RuntimeError(f"PDF extract failed: {e}")

@tool("pdf_get_info", "获取 PDF 元数据", category="document", requires_confirmation=False)
def pdf_get_info(file: str):
    """获取 PDF 基本信息（页数、大小等）"""
    try:
        from nano_pdf import get_info
        return get_info(file)
    except ImportError:
        raise RuntimeError("nano_pdf skill not installed")
    except Exception as e:
        raise RuntimeError(f"PDF info failed: {e}")

# ============================================
# Word 文档工具 (基于 docx)
# ============================================

@tool("docx_read", "读取 Word 文档", category="document", requires_confirmation=False)
def docx_read(file: str):
    """提取 .docx 文件内容"""
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        from pathlib import Path as _Path

        file_path = _Path(file)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file}")

        # 简单解析：提取 document.xml 中的文本
        with zipfile.ZipFile(file, 'r') as z:
            doc_xml = z.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            # 提取所有文本节点
            namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            texts = []
            for text in root.findall('.//w:t', namespaces):
                if text.text:
                    texts.append(text.text)
            content = '\n'.join(texts)
            return {
                "file": str(file_path),
                "content": content,
                "char_count": len(content)
            }
    except Exception as e:
        raise RuntimeError(f"DOCX read failed: {e}")

# ============================================
# Excel 工具 (基于 xlsx)
# ============================================

@tool("xlsx_read", "读取 Excel 文件", category="document", requires_confirmation=False)
def xlsx_read(file: str, sheet: str = None):
    """读取 .xlsx 文件内容"""
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        from pathlib import Path as _Path

        file_path = _Path(file)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file}")

        with zipfile.ZipFile(file, 'r') as z:
            # 读取共享字符串
            sst_xml = z.read('xl/sharedStrings.xml')
            sst_root = ET.fromstring(sst_xml)
            ns = {'sst': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            strings = []
            for si in sst_root.findall('.//sst:si', ns):
                text = ''.join([t.text for t in si.findall('.//sst:t', ns) if t.text])
                strings.append(text)

            # 读取工作表数据
            sheet_name = sheet or 'sheet1'
            sheet_xml = z.read(f'xl/worksheets/{sheet_name}.xml')
            sheet_root = ET.fromstring(sheet_xml)
            ns_sheet = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

            rows = []
            for row in sheet_root.findall('.//s:row', ns_sheet):
                cells = []
                for cell in row.findall('.//s:c', ns_sheet):
                    cell_type = cell.get('t')
                    cell_ref = cell.find('s:v', ns_sheet)
                    if cell_ref is not None:
                        value = cell_ref.text
                        if cell_type == 's':  # shared string
                            try:
                                idx = int(value)
                                value = strings[idx] if idx < len(strings) else value
                            except:
                                pass
                        cells.append(value)
                    else:
                        cells.append(None)
                rows.append(cells)

            return {
                "file": str(file_path),
                "sheet": sheet_name,
                "rows": len(rows),
                "cols": max(len(r) for r in rows) if rows else 0,
                "data": rows[:100]  # 只返回前100行预览
            }
    except Exception as e:
        raise RuntimeError(f"XLSX read failed: {e}")

# ============================================
# 注册完成
# ============================================

if __name__ == "__main__":
    print("📦 文档工具已注册")
    print("Tools:", ', '.join([t.name for t in registry._tools.values()]))
