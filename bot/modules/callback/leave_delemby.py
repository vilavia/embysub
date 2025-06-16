from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatMemberUpdated

from bot import bot, group, LOGGER, _open
from bot.func_helper.utils import tem_deluser, judge_have_bindsub
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby
from bot.sql_helper.sql_proxy_user import sql_delete_proxy_user
from bot.func_helper.emby import emby
import asyncio


@bot.on_chat_member_updated(filters.chat(group[0]))
async def leave_del_emby(_, event: ChatMemberUpdated):
    # 当用户加入群组时，old_chat_member 为 None，new_chat_member.status 为 MEMBER
    if (event.new_chat_member and event.new_chat_member.status == ChatMemberStatus.MEMBER and 
        event.old_chat_member is None):
        # 如果开关关闭，直接返回
        if not _open.check_sub_on_join:
            return

        user_id = event.new_chat_member.user.id
        user_fname = event.new_chat_member.user.first_name

        # 检查用户是否绑定了订阅
        has_sub = judge_have_bindsub(user_id)

        if not has_sub:
            try:
                # 发送警告消息
                warning_msg = await bot.send_message(
                    chat_id=event.chat.id,
                    text=f"⚠️ 用户 [{user_fname}](tg://user?id={user_id}) 加入了群组，但未绑定订阅！\n\n"
                         f"请在绑定订阅后，重新加入群组，您将30秒后被移出群组。"
                )

                LOGGER.info(
                    f"【入群检测】用户 {user_fname}({user_id}) 加入群组但未绑定订阅，已发送警告")

                # 等待 30 秒
                await asyncio.sleep(30)

                # 再次检查用户是否已绑定订阅
                has_sub_now = judge_have_bindsub(user_id)

                if not has_sub_now:
                    # 踢出用户
                    await bot.ban_chat_member(chat_id=event.chat.id, user_id=user_id)
                    # 立即解除封禁，这样用户可以再次加入
                    await bot.unban_chat_member(chat_id=event.chat.id, user_id=user_id)

                    # 发送通知消息
                    await bot.send_message(
                        chat_id=event.chat.id,
                        text=f"🚫 用户 [{user_fname}](tg://user?id={user_id}) 因未绑定订阅已被移出群组。\n\n"
                             f"请先绑定订阅后再加入群组。"
                    )

                    LOGGER.info(
                        f"【入群检测】用户 {user_fname}({user_id}) 未绑定订阅，已被移出群组")
                else:
                    # 用户已绑定订阅，发送欢迎消息
                    await bot.send_message(
                        chat_id=event.chat.id,
                        text=f"✅ 用户 [{user_fname}](tg://user?id={user_id}) 已成功绑定订阅，欢迎加入！"
                    )

                    LOGGER.info(
                        f"【入群检测】用户 {user_fname}({user_id}) 已绑定订阅，允许留在群组")

                # 删除警告消息
                await warning_msg.delete()

            except Exception as e:
                LOGGER.error(f"【入群检测】处理用户 {user_id} 时出错: {str(e)}")
        else:
            # 用户已绑定订阅，记录日志
            LOGGER.info(f"【入群检测】用户 {user_fname}({user_id}) 已绑定订阅，允许加入群组")
        return  # 处理完入群检测后直接返回，不再执行其他逻辑
    
    # 处理用户离开群组的情况
    if event.old_chat_member and not event.new_chat_member:
        if not event.old_chat_member.is_member and event.old_chat_member.user:
            user_id = event.old_chat_member.user.id
            user_fname = event.old_chat_member.user.first_name
            try:
                e = sql_get_emby(tg=user_id)
                if e is None or e.embyid is None:
                    return
                if await emby.emby_del(id=e.embyid):
                    sql_delete_proxy_user(tg=user_id)
                    sql_update_emby(Emby.embyid == e.embyid, embyid=None,
                                    name=None, pwd=None, pwd2=None, lv='d', cr=None, ex=None)
                    tem_deluser()
                    LOGGER.info(
                        f'【退群删号】- {user_fname}-{user_id} 已经离开了群组，咕噜噜，ta的账户被吃掉啦！')
                    await bot.send_message(chat_id=event.chat.id,
                                           text=f'✅ [{user_fname}](tg://user?id={user_id}) 已经离开了群组，咕噜噜，ta的账户被吃掉啦！')
                else:
                    LOGGER.error(
                        f'【退群删号】- {user_fname}-{user_id} 已经离开了群组，但是没能吃掉ta的账户，请管理员检查！')
                    await bot.send_message(chat_id=event.chat.id,
                                           text=f'❎ [{user_fname}](tg://user?id={user_id}) 已经离开了群组，但是没能吃掉ta的账户，请管理员检查！')
                if _open.leave_ban:
                    await bot.ban_chat_member(chat_id=event.chat.id, user_id=user_id)
            except Exception as e:
                LOGGER.error(f"【退群删号】- {user_id}: {e}")
            else:
                pass
        return  # 处理完退群后直接返回
    # 处理用户被封禁的情况
    if event.old_chat_member and event.new_chat_member and event.new_chat_member.status is ChatMemberStatus.BANNED:
        user_id = event.new_chat_member.user.id
        user_fname = event.new_chat_member.user.first_name
        try:
            e = sql_get_emby(tg=user_id)
            if e is None or e.embyid is None:
                return
            if await emby.emby_del(id=e.embyid):
                sql_delete_proxy_user(tg=user_id)
                sql_update_emby(Emby.embyid == e.embyid, embyid=None, name=None, pwd=None, pwd2=None, lv='d', cr=None,
                                ex=None)
                tem_deluser()
                LOGGER.info(
                    f'【退群删号】- {user_fname}-{user_id} 已经离开了群组，咕噜噜，ta的账户被吃掉啦！')
                await bot.send_message(chat_id=event.chat.id,
                                       text=f'✅ [{user_fname}](tg://user?id={user_id}) 已经离开了群组，咕噜噜，ta的账户被吃掉啦！')
            else:
                LOGGER.error(
                    f'【退群删号】- {user_fname}-{user_id} 已经离开了群组，但是没能吃掉ta的账户，请管理员检查！')
                await bot.send_message(chat_id=event.chat.id,
                                       text=f'❎ [{user_fname}](tg://user?id={user_id}) 已经离开了群组，但是没能吃掉ta的账户，请管理员检查！')
            if _open.leave_ban:
                await bot.ban_chat_member(chat_id=event.chat.id, user_id=user_id)
        except Exception as e:
            LOGGER.error(f"【退群删号】- {user_id}: {e}")
        else:
            pass
        return  # 处理完封禁后直接返回