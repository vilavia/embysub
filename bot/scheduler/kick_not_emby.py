from bot import bot, LOGGER, group, admins
from bot.sql_helper.sql_emby import get_all_emby, Emby, sql_get_emby
from datetime import datetime, timedelta
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, FloodWait, PeerIdInvalid
import asyncio


async def kick_not_emby():
    """
    踢出没有 emby 账号的用户
    """
    LOGGER.info("开始执行踢出没有 emby 账号的用户任务")

    # 获取所有有 Emby 账号的用户 ID
    all_emby_users = get_all_emby(Emby.embyid != None and Emby.embyid != '')
    emby_user_ids = set()
    for user in all_emby_users:
        emby_user_ids.add(user.tg)

    LOGGER.info(f"系统中共有 {len(emby_user_ids)} 名用户拥有 Emby 账号")

    chat_id = group[0]
    try:
        chat_id = int(chat_id)
        # 获取群组信息
        try:
            chat = await bot.get_chat(chat_id)
            chat_title = chat.title
            LOGGER.info(f"正在检查群组: {chat_title} ({chat_id})")
        except PeerIdInvalid:
            LOGGER.error(f"无法获取群组信息: {chat_id}，可能是群组ID无效")
            return
        except Exception as e:
            LOGGER.error(f"获取群组 {chat_id} 信息时出错: {str(e)}")
            return

        # 获取群组成员
        members = []
        try:
            async for member in bot.get_chat_members(chat_id):
                if not member.user.is_bot and not member.user.is_deleted and member.user.id not in admins:
                    members.append(member)

            LOGGER.info(
                f"群组 {chat_title} 共有 {len(members)} 名成员（不包括管理员和机器人）")
        except Exception as e:
            LOGGER.error(f"获取群组 {chat_id} 成员时出错: {str(e)}")
            return

        # 检查每个成员是否有 emby 账号
        kicked_count = 0
        no_emby_users = []

        for member in members:
            user_id = member.user.id
            user_name = member.user.first_name

            # 检查用户是否有 emby 账号
            if user_id not in emby_user_ids:
                no_emby_users.append((user_id, user_name))

        # 发送预警消息
        if no_emby_users:
            warning_msg = "⚠️ 以下用户没有 Emby 账号，将被移出群组：\n\n"
            for user_id, user_name in no_emby_users:
                warning_msg += f"• [{user_name}](tg://user?id={user_id})\n"

            warning_msg += "\n如有误判，请联系管理员。"

            try:
                await bot.send_message(chat_id, warning_msg)
                LOGGER.info(f"已发送预警消息到群组 {chat_title}")
            except Exception as e:
                LOGGER.error(f"发送预警消息到群组 {chat_id} 时出错: {str(e)}")

            # 再次检查用户是否有 Emby 账号（可能在这段时间内注册了）
            for user_id, user_name in no_emby_users:
                # 再次检查用户是否有 emby 账号
                emby_user = sql_get_emby(tg=user_id)

                # 如果用户没有 emby 账号或 emby_id 为空，踢出用户
                if emby_user is None or emby_user.embyid is None:
                    try:
                        # 踢出用户
                        await bot.ban_chat_member(chat_id, user_id, until_date=datetime.now() + timedelta(minutes=1))
                        # 发送通知消息
                        await bot.send_message(
                            chat_id,
                            f"👮‍♂️ 用户 [{user_name}](tg://user?id={user_id}) 因没有 Emby 账号已被移出群组。"
                        )

                        LOGGER.info(
                            f"已踢出用户 {user_name} ({user_id}) - 没有 Emby 账号")
                        kicked_count += 1

                        # 避免触发 Telegram 限制
                        await asyncio.sleep(2)
                    except UserNotParticipant:
                        LOGGER.info(f"用户 {user_name} ({user_id}) 已不在群组中")
                    except ChatAdminRequired:
                        LOGGER.error(
                            f"无法踢出用户 {user_name} ({user_id}) - 需要管理员权限")
                    except FloodWait as e:
                        LOGGER.warning(f"触发 FloodWait，等待 {e.value} 秒")
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        LOGGER.error(
                            f"踢出用户 {user_name} ({user_id}) 时出错: {str(e)}")

        # 发送总结消息
        if kicked_count > 0:
            await bot.send_message(
                chat_id,
                f"🧹 清理完成：已移除 {kicked_count} 名没有 Emby 账号的用户。"
            )
            LOGGER.info(f"群组 {chat_title} 清理完成，共踢出 {kicked_count} 名用户")
        else:
            LOGGER.info(f"群组 {chat_title} 中所有用户都有 Emby 账号")

    except Exception as e:
        LOGGER.error(f"处理群组 {chat_id} 时出错: {str(e)}")

    LOGGER.info("踢出没有 emby 账号的用户任务执行完毕")
