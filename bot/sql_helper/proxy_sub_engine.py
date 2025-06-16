"""
初始化数据库
"""
from bot import proxy_sub_config, LOGGER
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from typing import List, Dict, Optional
plugin_status = proxy_sub_config.status
if not plugin_status:
    LOGGER.info("✈️订阅功能未开启")
# 创建engine对象
engine = create_engine(f"mysql+pymysql://{proxy_sub_config.proxy_sub_db_config.db_user}:{proxy_sub_config.proxy_sub_db_config.db_pwd}@{proxy_sub_config.proxy_sub_db_config.db_host}:{proxy_sub_config.proxy_sub_db_config.db_port}/{proxy_sub_config.proxy_sub_db_config.db_name}?utf8mb4", echo=False,
                       echo_pool=False,
                       pool_size=16,
                       pool_recycle=60 * 30,
                       )

# 调用sql_start()函数，返回一个Session对象
def sql_start() -> scoped_session:
    return scoped_session(sessionmaker(bind=engine, autoflush=False))


Session = sql_start()

def get_all_sub() -> List[Dict]:
    """
    获取所有订阅信息
    返回格式: [{'id': xxx, 'token': xxx, 'expired_at': xxx}, ...]
    """
    try:
        with Session() as session:
            sql = text(proxy_sub_config.proxy_sub_db_config.get_all_sub_sql)
            result = session.execute(sql).mappings()
            return [dict(row) for row in result]
    except Exception as e:
        LOGGER.error(f"获取所有订阅信息失败: {str(e)}")
        return []

def get_sub_by_token(token: str) -> Optional[Dict]:
    """
    根据token获取订阅信息
    返回格式: {'id': xxx, 'token': xxx, 'expired_at': xxx} 或 None
    """
    try:
        with Session() as session:
            sql = text(proxy_sub_config.proxy_sub_db_config.get_sub_by_token_sql)
            result = session.execute(sql, {'token': token}).mappings().first()
            if not result:
                return None
            return dict(result)
    except Exception as e:
        LOGGER.error(f"根据token获取订阅信息失败: {str(e)}")
        return None

