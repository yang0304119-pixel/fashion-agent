"""
种子数据脚本

向数据库填充初始数据：3 个测试用户 + 6 款男装羽绒服 + 6 个订单。
幂等运行——库中已有数据时自动跳过。

用法：
    python scripts/seed_data.py

验证：
    sqlite3 data/fashion.db "SELECT count(*) FROM product;"  # 应返回 6
"""

import logging
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保直接运行时能导入 app
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import init_db, SessionLocal
from app.models import Tenant, User, Product, Order

logger = logging.getLogger(__name__)


# ── 种子数据 ──────────────────────────────────────────────

# 默认租户：服装方向测试店铺
TENANTS = [
    {"id": 1, "name": "默认测试店铺", "industry": "服装", "contact": "张店主"},
]

USERS = [
    {"id": 1, "username": "张三"},
    {"id": 2, "username": "李四"},
    {"id": 3, "username": "王五"},
]

# tenant_id=1 关联到默认测试店铺
PRODUCTS = [
    {
        "id": 1,
        "tenant_id": 1,
        "name": "极寒系列加厚羽绒服",
        "category": "羽绒服",
        "price": 499.00,
        "colors": ["黑色", "深灰"],
        "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
        "description": "专为极寒天气设计的高性能羽绒服。采用防风防泼水面料，有效阻挡寒风和湿气。加厚充绒设计，提供卓越保暖效果，适合东北地区及高寒环境穿着。",
        "materials": "面料：100%聚酯纤维（防风防泼水涂层）；里料：100%聚酯纤维；填充物：90%白鹅绒、10%羽毛；充绒量：200g+",
        "care_instructions": "建议干洗；不可漂白；不可熨烫；悬挂晾干；存放时请使用宽肩衣架，避免长时间压缩。",
        "stock": 50,
    },
    {
        "id": 2,
        "tenant_id": 1,
        "name": "轻薄都市羽绒服",
        "category": "羽绒服",
        "price": 299.00,
        "colors": ["深灰", "藏青"],
        "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
        "description": "适合春秋季和初冬穿着的轻薄羽绒服。轻量化设计，整衣重量仅约300g，可轻松收纳进附赠的压缩袋。简约外观适合日常通勤和商务差旅。",
        "materials": "面料：100%尼龙（防钻绒处理）；里料：100%聚酯纤维；填充物：80%白鸭绒、20%羽毛；充绒量：80g（M码）",
        "care_instructions": "30°C以下温水洗涤；不可漂白；低温熨烫；不可干洗；平铺晾干，避免暴晒。",
        "stock": 120,
    },
    {
        "id": 3,
        "tenant_id": 1,
        "name": "户外三合一冲锋羽绒服",
        "category": "羽绒服",
        "price": 459.00,
        "colors": ["军绿", "黑色"],
        "sizes": ["M", "L", "XL", "2XL", "3XL"],
        "description": "三合一设计：外层防风防水冲锋衣壳 + 内层可拆卸轻薄羽绒内胆。一衣三穿，适应多种天气和场景，是户外爱好者的理想选择。",
        "materials": "外壳面料：100%聚酯纤维（防水透气膜）；内胆面料：100%尼龙；内胆填充物：85%白鸭绒、15%羽毛；充绒量：120g（M码）",
        "care_instructions": "外壳与内胆分开洗涤；外壳用专业冲锋衣洗涤剂；内胆参照轻薄羽绒服洗护方式；洗后自然晾干，不可烘干。",
        "stock": 35,
    },
    {
        "id": 4,
        "tenant_id": 1,
        "name": "商务修身羽绒服",
        "category": "羽绒服",
        "price": 399.00,
        "colors": ["藏青", "深灰"],
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "description": "专为商务人士设计的修身款羽绒服。简洁利落的剪裁线条，可在商务和休闲场景之间自由切换。适中的保暖性能满足城市冬季通勤需求。",
        "materials": "面料：88%聚酯纤维、12%氨纶（四面弹力面料）；里料：100%聚酯纤维；填充物：90%白鸭绒、10%羽毛；充绒量：150g（M码）",
        "care_instructions": "建议干洗以保持版型；不可漂白；低温熨烫；不可用力拧干；悬挂阴干。",
        "stock": 25,
    },
    {
        "id": 5,
        "tenant_id": 1,
        "name": "连帽短款羽绒服",
        "category": "羽绒服",
        "price": 259.00,
        "colors": ["卡其", "黑色"],
        "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
        "description": "休闲风格短款连帽羽绒服，衣长在腰线附近，视觉上拉长腿部比例。可拆卸帽子设计，一衣两穿。高性价比之选。",
        "materials": "面料：100%聚酯纤维（防泼水处理）；里料：100%聚酯纤维；填充物：80%白鸭绒、20%羽毛；充绒量：100g（M码）",
        "care_instructions": "30°C以下温水洗涤；不可漂白；低温熨烫；不可干洗；洗后轻轻挤干水分，平铺晾干。",
        "stock": 80,
    },
    {
        "id": 6,
        "tenant_id": 1,
        "name": "加长保暖羽绒服",
        "category": "羽绒服",
        "price": 359.00,
        "colors": ["黑色", "深灰"],
        "sizes": ["M", "L", "XL", "2XL", "3XL"],
        "description": "过膝长款设计，全方位保暖。适合北方严寒地区冬季日常穿着。腰部可调节抽绳，灵活控制松紧。两侧大容量口袋带绒里，暖手又实用。",
        "materials": "面料：100%聚酯纤维（高密度防钻绒）；里料：100%聚酯纤维；填充物：85%白鸭绒、15%羽毛；充绒量：180g（M码）",
        "care_instructions": "30°C以下温水洗涤；不可漂白；低温熨烫；不可干洗；建议使用中性洗涤剂；晾干后轻拍使羽绒蓬松。",
        "stock": 40,
    },
]

ORDERS = [
    # id 从 10001 开始，模拟真实订单号
    {"id": 10001, "tenant_id": 1, "user_id": 1, "product_id": 1, "quantity": 1, "total_price": 499.00, "status": "shipped"},
    {"id": 10002, "tenant_id": 1, "user_id": 1, "product_id": 2, "quantity": 2, "total_price": 598.00, "status": "delivered"},
    {"id": 10003, "tenant_id": 1, "user_id": 2, "product_id": 4, "quantity": 1, "total_price": 399.00, "status": "pending"},
    {"id": 10004, "tenant_id": 1, "user_id": 2, "product_id": 3, "quantity": 1, "total_price": 459.00, "status": "refunded"},
    {"id": 10005, "tenant_id": 1, "user_id": 3, "product_id": 5, "quantity": 1, "total_price": 259.00, "status": "shipped"},
    {"id": 10006, "tenant_id": 1, "user_id": 3, "product_id": 6, "quantity": 2, "total_price": 718.00, "status": "delivered"},
]


# ── 执行逻辑 ──────────────────────────────────────────────

def seed_database():
    """初始化数据库并填充种子数据。幂等——已有数据时跳过。"""
    init_db()
    db = SessionLocal()
    try:
        # 检查是否已有数据
        if db.query(User).count() > 0:
            print("[OK] 数据库已有数据，跳过种子初始化")
            return

        # 按依赖顺序插入：tenant → user → product → order
        print("[INFO] 正在插入租户数据...")
        for tenant_data in TENANTS:
            db.add(Tenant(**tenant_data))
        db.flush()

        print("[INFO] 正在插入用户数据...")
        for user_data in USERS:
            db.add(User(**user_data))
        db.flush()

        print("[INFO] 正在插入商品数据...")
        for product_data in PRODUCTS:
            db.add(Product(**product_data))
        db.flush()

        print("[INFO] 正在插入订单数据...")
        for order_data in ORDERS:
            db.add(Order(**order_data))

        db.commit()

        # 打印摘要
        print(f"\n{'='*40}")
        print(f"种子数据初始化完成！")
        print(f"{'='*40}")
        print(f"  租户：{db.query(Tenant).count()} 家")
        print(f"  用户：{db.query(User).count()} 人")
        print(f"  商品：{db.query(Product).count()} 款")
        print(f"  订单：{db.query(Order).count()} 单")
        print(f"{'='*40}")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 种子数据插入失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_database()
