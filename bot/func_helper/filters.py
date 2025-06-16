#!/usr/bin/python3
from pyrogram.errors import BadRequest
from pyrogram.filters import create
from bot import admins, owner, group, LOGGER
from pyrogram.enums import ChatMemberStatus


# async def owner_filter(client, update):
#     """
#     过滤 owner
#     :param client:
#     :param update:
#     :return:
#     """
#     user = update.from_user or update.sender_chat
#     uid = user.id
#     return uid == owner

# 三个参数给on用
async def admins_on_filter(filt, client, update) -> bool:
    """
    过滤admins中id，包括owner
    :param client:
    :param update:
    :return:
    """
    user = update.from_user or update.sender_chat
    uid = user.id
    return bool(uid == owner or uid in admins or uid in group)


async def admins_filter(update):
    """
    过滤admins中id，包括owner
    """
    user = update.from_user or update.sender_chat
    uid = user.id
    return bool(uid == owner or uid in admins)


async def user_in_group_filter(client, update):
    """
    过滤在授权组中的人员
    :param client:
    :param update:
    :return:
    """
    uid = update.from_user or update.sender_chat
    uid = uid.id
    for i in group:
        try:
            u = await client.get_chat_member(chat_id=int(i), user_id=uid)
            if u.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER, ChatMemberStatus.OWNER]:
                return True
            elif u.status == ChatMemberStatus.BANNED:
                return False
        except BadRequest as e:
            if e.ID == 'USER_NOT_PARTICIPANT':
                return False
            elif e.ID == 'CHAT_ADMIN_REQUIRED':
                LOGGER.error(f"bot不能在 {i} 中工作，请检查bot是否在群组及其权限设置")
                return False
            else:
                return False
        else:
            continue
    return False


async def user_in_group_on_filter(filt, client, update):
    """
    过滤在授权组中的人员
    :param client:
    :param update:
    :return:
    """
    uid = update.from_user or update.sender_chat
    uid = uid.id
    if uid in group:
        return True
    for i in group:
        try:
            u = await client.get_chat_member(chat_id=int(i), user_id=uid)
            if u.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER,
                            ChatMemberStatus.OWNER]:  # 移除了 'ChatMemberStatus.RESTRICTED' 防止有人进群直接注册不验证
                return True  # 因为被限制用户无法使用bot，所以需要检查权限。
            elif u.status == ChatMemberStatus.BANNED:
                await client.send_message(chat_id=uid, text=f'🫡您已被加入黑名单，无法使用bot！')
                return False
        except BadRequest as e:
            if e.ID == 'USER_NOT_PARTICIPANT':
                await client.send_message(chat_id=uid, text=f'🫡您不在群组中，请先加入群组再来叭')
                return False
            elif e.ID == 'CHAT_ADMIN_REQUIRED':
                LOGGER.error(f"bot不能在 {i} 中工作，请检查bot是否在群组及其权限设置")
                return False
            else:
                return False
        except Exception as e:
            return False
    return False


# 过滤 on_message or on_callback 的admin
admins_on_filter = create(admins_on_filter)
admins_filter = create(admins_filter)

# 过滤 是否在群内
user_in_group_f = create(user_in_group_filter)
user_in_group_on_filter = create(user_in_group_on_filter)
