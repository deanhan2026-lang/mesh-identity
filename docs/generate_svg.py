# 生成 MeshIdentity 架构图 SVG
# 纯 Python + 标准库，无需任何依赖

import xml.etree.ElementTree as ET
from datetime import datetime


def create_svg_doc():
    """创建架构图 SVG"""
    svg_id = 'svg-root'
    
    svg = ET.Element('svg', {
        'xmlns': 'http://www.w3.org/2000/svg',
        'viewBox': '0 0 1000 700',
        'width': '1000',
        'height': '700',
        'id': svg_id,
        'style': 'font-family: -apple-system, "Microsoft YaHei", sans-serif;'
    })
    
    # 背景
    bg_grad = ET.SubElement(svg, 'linearGradient', {'id': 'bg-grad', 'x1': '0%', 'y1': '0%', 'x2': '100%', 'y2': '100%'})
    ET.SubElement(bg_grad, 'stop', {'offset': '0%', 'stop-color': '#0a0a1a'})
    ET.SubElement(bg_grad, 'stop', {'offset': '100%', 'stop-color': '#1a1a3e'})
    
    ET.SubElement(svg, 'rect', {'width': '1000', 'height': '700', 'fill': 'url(#bg-grad)'})
    
    # 标题
    ET.SubElement(svg, 'text', {'x': '500', 'y': '40', 'text-anchor': 'middle', 'fill': '#e94560', 'font-size': '22', 'font-weight': 'bold'}).text = 'MeshIdentity 架构图'
    ET.SubElement(svg, 'text', {'x': '500', 'y': '58', 'text-anchor': 'middle', 'fill': '#888', 'font-size': '12'}).text = 'Local Agent Multi-Terminal Identity & Memory Sync'

    # 阴影滤镜
    shadow = ET.SubElement(svg, 'filter', {'id': 'shadow', 'x': '-5%', 'y': '-5%', 'width': '115%', 'height': '115%'})
    ET.SubElement(shadow, 'feDropShadow', {'dx': '2', 'dy': '3', 'stdDeviation': '4', 'flood-color': 'rgba(0,0,0,0.4)'})

    # 箭头定义
    arrow = ET.SubElement(svg, 'marker', {'id': 'arrow', 'viewBox': '0 0 10 10', 'refX': '8', 'refY': '5', 'markerWidth': '6', 'markerHeight': '6', 'orient': 'auto'})
    ET.SubElement(arrow, 'path', {'d': 'M 0 0 L 10 5 L 0 10 z', 'fill': '#e94560'})
    
    arrow_p = ET.SubElement(svg, 'marker', {'id': 'arrow-p', 'viewBox': '0 0 10 10', 'refX': '8', 'refY': '5', 'markerWidth': '6', 'markerHeight': '6', 'orient': 'auto'})
    ET.SubElement(arrow_p, 'path', {'d': 'M 0 0 L 10 5 L 0 10 z', 'fill': '#533483'})

    def box(x, y, w, h, fill, stroke, label, items=None):
        """绘制圆角矩形盒子"""
        ET.SubElement(svg, 'rect', {'x': str(x), 'y': str(y), 'width': str(w), 'height': str(h), 'rx': '8', 'ry': '8', 'fill': fill, 'stroke': stroke, 'stroke-width': '1.5', 'filter': 'url(#shadow)'})
        
        if label:
            ET.SubElement(svg, 'text', {'x': str(x + w//2), 'y': str(y + 20), 'text-anchor': 'middle', 'fill': '#fff', 'font-size': '11', 'font-weight': 'bold'}).text = label
        
        if items:
            for i, (name, color) in enumerate(items):
                ix = x + 12 + i * 50
                iy = y + 35
                ET.SubElement(svg, 'rect', {'x': str(ix), 'y': str(iy), 'width': '38', 'height': '22', 'rx': '4', 'ry': '4', 'fill': color, 'opacity': '0.9'})
                ET.SubElement(svg, 'text', {'x': str(ix + 19), 'y': str(iy + 15), 'text-anchor': 'middle', 'fill': '#fff', 'font-size': '9'}).text = name

    def label(x, y, text, color='#fff', size='10', anchor='middle', bold=False):
        """绘制文字"""
        attrs = {'x': str(x), 'y': str(y), 'text-anchor': anchor, 'fill': color, 'font-size': size}
        if bold:
            attrs['font-weight'] = 'bold'
        ET.SubElement(svg, 'text', attrs).text = text

    def line(x1, y1, x2, y2, color='#e94560', width='1.5', dash=None):
        """绘制线段"""
        attrs = {'x1': str(x1), 'y1': str(y1), 'x2': str(x2), 'y2': str(y2), 'stroke': color, 'stroke-width': width}
        if dash:
            attrs['stroke-dasharray'] = dash
        ET.SubElement(svg, 'line', attrs)

    # ========== CLI 层 ==========
    y_cli = 85
    box(70, y_cli, 860, 65, 'url(#bg-grad)', '#e94560', '📟 CLI (mesh-id)',
        [('init', '#e94560'), ('sync', '#0f3460'), ('scene', '#533483'), ('status', '#2d1b69'), ('conflict', '#e94560')])

    # CLI → 核心层箭头
    line(500, 150, 500, 175)

    # ========== 核心层 ==========
    y_core = 185
    box(70, y_core, 860, 125, 'transparent', '#0f3460', '⚙️ 核心层')
    label(500, y_core + 16, '⚙️ 核心层', '#0f3460', '11', 'middle', True)

    # DID Manager
    bx_did = 80
    box(bx_did, y_core + 28, 270, 90, '#16213e', '#0f3460', None)
    label(215, y_core + 48, '🔑 DID Manager', '#fff', '13', 'middle', True)
    label(215, y_core + 66, 'Ed25519 密钥对  |  soul_anchor', '#aaa', '10')
    label(215, y_core + 82, 'DID生成/验证  |  签名/验签', '#aaa', '10')
    label(215, y_core + 98, '私钥加密存储 (方案一)', '#888', '9')

    # Memory Sync
    bx_sync = 365
    box(bx_sync, y_core + 28, 270, 90, '#16213e', '#0f3460', None)
    label(500, y_core + 48, '🔄 Memory Sync', '#fff', '13', 'middle', True)
    label(500, y_core + 66, '双向同步  |  向量时钟', '#aaa', '10')
    label(500, y_core + 82, '冲突检测  |  LWW策略', '#aaa', '10')
    label(500, y_core + 98, '人工审核接口', '#888', '9')

    # Scene Adapter
    bx_scene = 650
    box(bx_scene, y_core + 28, 270, 90, '#16213e', '#0f3460', None)
    label(785, y_core + 48, '🎯 Scene Adapter', '#fff', '13', 'middle', True)
    label(785, y_core + 66, '工作 / 个人 / 开发', '#aaa', '10')
    label(785, y_core + 82, 'Polaris阈值自适应', '#aaa', '10')
    label(785, y_core + 98, '自定义场景拓展', '#888', '9')

    # 核心层 → 存储层箭头
    for cx in [215, 500, 785]:
        line(cx, 310, cx, 345, '#533483', '1.5')
        # 箭头头
        ET.SubElement(svg, 'use', {'href': '#arrow-p', 'x': str(cx-5), 'y': '338'})

    # ========== 存储抽象层 ==========
    y_stor = 355
    box(70, y_stor, 860, 80, '#0f3460', '#533483', '💾 存储抽象层 (NAS Storage)')
    label(500, y_stor + 45, 'SMB / NFS 抽象接口  ·  文件锁机制  ·  健康检查', '#aaa')

    # 存储层 → NAS 箭头
    line(500, 435, 500, 460)

    # ========== NAS 共享存储 ==========
    y_nas = 470
    box(70, y_nas, 860, 130, '#2d1b69', '#e94560', '🌐 共享存储 (NAS)')

    nas_items = [
        (140, 'did/', 'DID凭证  公钥', '#e94560'),
        (330, 'memory_vault/', '结构化记忆', '#0f3460'),
        (520, 'scene_config/', '场景配置', '#533483'),
        (710, 'lock/', '文件锁', '#4a2c8a'),
    ]
    for nx, name, desc, color in nas_items:
        ET.SubElement(svg, 'rect', {'x': str(nx), 'y': str(y_nas + 35), 'width': '160', 'height': '45', 'rx': '6', 'ry': '6', 'fill': color, 'opacity': '0.8'})
        label(nx + 80, y_nas + 52, name, '#fff', '11', 'middle', True)
        label(nx + 80, y_nas + 70, desc, 'rgba(255,255,255,0.7)', '9', 'middle')

    # ========== 多终端 ==========
    y_term = 620
    box(70, y_term, 860, 55, '#1a1a2e', '#e94560', None)
    label(500, y_term + 20, '🖥️ 多终端', '#fff', '11', 'middle', True)

    terminals = [(250, 'Windows Nyx'), (500, 'Mac Nyx'), (750, 'NAS Agent')]
    for tx, tname in terminals:
        line(tx, 600, tx, 620, '#e94560', '1', '4,3')
        label(tx, y_term + 42, tname, '#aaa', '10', 'middle')

    # ========== 底部文字 ==========
    label(70, 685, f'MeshIdentity v0.1.0  ·  公开日期: {datetime.now().strftime("%Y-%m-%d")}', '#555', '9', 'start')
    label(930, 685, 'MIT License  ·  github.com/deanhan2026-lang/mesh-identity', '#555', '9', 'end')

    return svg


# 写入文件
svg = create_svg_doc()
tree = ET.ElementTree(svg)
output_path = r'C:\Users\Administrator\.qclaw\workspace-agent-d9479bde\mesh-identity-sync\docs\architecture.svg'
tree.write(output_path, encoding='utf-8', xml_declaration=True)

import os
size = os.path.getsize(output_path)
print(f"✅ SVG架构图已生成: {output_path}")
print(f"   文件大小: {size} bytes")
print(f"   可以用浏览器打开查看")
print(f"   或直接作为知乎文章配图")
