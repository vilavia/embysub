from sqlalchemy import Column, String, BigInteger, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from bot.sql_helper import Base, Session, engine
Base = declarative_base()

class ProxyUser(Base):
    __tablename__ = 'proxy_user'
    tg = Column(BigInteger, primary_key=True, autoincrement=False)
    id = Column(BigInteger, unique=True, nullable=False)
    token = Column(String(255), nullable=False)
    expired_at = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    bind_url = Column(String(255), nullable=False)
    @property
    def is_bound(self) -> bool:
        # 判断id和token是否都不为空
        return self.id is not None and self.id != "" and self.token is not None and self.token != ""

    @property
    def is_expired(self) -> bool:
        # 如果expired_at为None，认为是永久订阅
        if self.expired_at is None:
            return False
        elif self.expired_at == -1:
            return True
        else:
            return self.expired_at > int(datetime.now().timestamp())

ProxyUser.__table__.create(bind=engine, checkfirst=True)

def sql_add_proxy_user(tg: int, id: int, token: str, expired_at: int, bind_url: str):
    """
    添加一条代理用户记录
    """
    with Session() as session:
        session.add(ProxyUser(tg=tg, id=id, token=token, expired_at=expired_at, bind_url=bind_url))
        session.commit()

def sql_delete_proxy_user(tg: int):
    """
    删除一条代理用户记录
    """
    with Session() as session:
        session.query(ProxyUser).filter(ProxyUser.tg == tg).delete()
        session.commit()
def sql_get_proxy_user_by_tg(tg: int):
    """
    获取一条代理用户记录
    """
    with Session() as session:
        return session.query(ProxyUser).filter(ProxyUser.tg == tg).first()
def sql_get_proxy_user_by_token(token: str):
    """
    获取一条代理用户记录
    """
    with Session() as session:
        return session.query(ProxyUser).filter(ProxyUser.token == token).first()
def sql_update_proxy_user(tg: int, id: int, token: str, expired_at, bind_url: str):
    """
    更新一条代理用户记录
    """
    with Session() as session:
        session.query(ProxyUser).filter(ProxyUser.tg == tg).update({ProxyUser.id: id, ProxyUser.token: token, ProxyUser.expired_at: expired_at, ProxyUser.bind_url: bind_url})
        session.commit()
def sql_update_proxy_user_expired_at(tg: int, expired_at):
    """
    更新一条代理用户记录
    """
    with Session() as session:
        session.query(ProxyUser).filter(ProxyUser.tg == tg).update({ProxyUser.expired_at: expired_at})
        session.commit()

def sql_update_proxy_user_bind_url(tg: int, bind_url: str):
    """
    更新一条代理用户记录
    """
    with Session() as session:
        session.query(ProxyUser).filter(ProxyUser.tg == tg).update({ProxyUser.bind_url: bind_url})
        session.commit()

def sql_update_proxy_user_id(tg: int, id: int):
    """
    更新一条代理用户记录
    """
    with Session() as session:
        session.query(ProxyUser).filter(ProxyUser.tg == tg).update({ProxyUser.id: id})
        session.commit()

def sql_get_all_proxy_users():
    """
    获取所有代理用户记录
    """
    with Session() as session:
        return session.query(ProxyUser).all()
