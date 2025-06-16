"""
定时同步订阅到期时间到Emby账户
"""
from datetime import datetime, timedelta
from pyrogram.errors import FloodWait
from asyncio import sleep
from bot import LOGGER, proxy_sub_config, bot, group
from bot.sql_helper.proxy_sub_engine import get_all_sub
from bot.sql_helper.sql_proxy_user import sql_get_all_proxy_users, sql_update_proxy_user_expired_at, sql_delete_proxy_user
from bot.sql_helper.sql_emby import sql_update_emby, sql_get_emby, Emby, get_all_emby
from bot.func_helper.emby import emby
from bot.func_helper.utils import tem_deluser


async def sync_sub_expire():
    """同步订阅到期时间到Emby账户"""
    if not proxy_sub_config.status:
        LOGGER.info("✈️ 订阅功能未开启，跳过同步")
        return "✈️ 订阅功能未开启，跳过同步"

    try:
        LOGGER.info("✈️ 开始同步订阅到期时间...")

        # 获取所有订阅信息
        sub_list = get_all_sub()
        if not sub_list:
            sub_list = []
            LOGGER.warning("✈️ 没有找到订阅信息")

        # 获取所有代理用户
        proxy_users = sql_get_all_proxy_users()
        if not proxy_users:
            proxy_users = []

        # 创建id到订阅信息的映射
        sub_map = {sub.get('id'): sub for sub in sub_list}
        now = datetime.now()
        dead_day = now + timedelta(days=5)

        renew_count = 0
        del_count = 0
        ban_count = 0
        chat_id = group[0]
        
        # 创建TG ID到代理用户的映射，用于后续检查未绑定订阅的账号
        tg_to_proxy_user = {user.tg: user for user in proxy_users}
        
        for user in proxy_users:
            if not user.is_bound:
                continue

            # 查找对应的订阅信息
            sub_info = sub_map.get(user.id)
            if not sub_info:
                LOGGER.warning(f"✈️ 用户 {user.tg} 的订阅 {user.id} 未找到")
                continue

            # 获取订阅到期时间
            expired_at = sub_info.get('expired_at')
            sql_update_proxy_user_expired_at(user.tg, expired_at)
            # 处理永久订阅
            if expired_at == 0 or expired_at is None:
                # 设置为10年后
                emby_ex = now.replace(year=now.year + 10)
                is_expired = False
            else:
                # 转换时间戳为datetime
                emby_ex = datetime.fromtimestamp(expired_at)
                is_expired = emby_ex < now
            # 获取用户Emby信息
            emby_info = sql_get_emby(tg=user.tg)
            sql_update_emby(Emby.tg == user.tg, ex=emby_ex)
            if not emby_info or not emby_info.embyid:
                LOGGER.warning(f"✈️ 用户 {user.tg} 没有Emby账户信息")
                continue
            # 处理到期情况
            if is_expired:
                # 如果已经是禁用状态，检查是否超过5天需要删除
                if emby_info.lv == 'c':
                    delta = emby_info.ex + timedelta(days=5)
                    if now >= delta:
                        # 超过5天，删除账户
                        if await emby.emby_del(emby_info.embyid):
                            sql_update_emby(Emby.embyid == emby_info.embyid, embyid=None, name=None,
                                            pwd=None, pwd2=None, lv='d', cr=None, ex=None)
                            tem_deluser()
                            sql_delete_proxy_user(user.tg)
                            # 踢出用户
                            await bot.ban_chat_member(chat_id, user.tg, until_date=datetime.now() + timedelta(minutes=1))
                            text = f'【订阅同步】\n#id{user.tg} 删除账户 [{emby_info.name}](tg://user?id={user.tg})\n已到期 5 天，执行清除任务。'
                            LOGGER.info(text)
                            try:
                                send = await bot.send_message(user.tg, text)
                                # await send.forward(chat_id)
                            except FloodWait as f:
                                LOGGER.warning(str(f))
                                await sleep(f.value * 1.2)
                                send = await bot.send_message(user.tg, text)
                                # await send.forward(chat_id)
                            except Exception as e:
                                LOGGER.error(e)
                            del_count += 1
                else:
                    # 如果不是禁用状态，禁用账户
                    if await emby.emby_change_policy(emby_info.embyid, method=True):
                        if sql_update_emby(Emby.tg == user.tg, lv='c'):
                            text = f'【订阅同步】\n#id{user.tg} 到期禁用 [{emby_info.name}](tg://user?id={user.tg})\n将为您封存至 {dead_day.strftime("%Y-%m-%d")}，请及时续期'
                            LOGGER.info(text)
                            try:
                                send = await bot.send_message(user.tg, text)
                                # await send.forward(chat_id)
                            except FloodWait as f:
                                LOGGER.warning(str(f))
                                await sleep(f.value * 1.2)
                                send = await bot.send_message(user.tg, text)
                                # await send.forward(chat_id)
                            except Exception as e:
                                LOGGER.error(e)
                            ban_count += 1
                        else:
                            LOGGER.warning(f"✈️ 用户 {user.tg} 禁用状态更新失败")
                    else:
                        LOGGER.error(f"✈️ 用户 {user.tg} Emby API禁用操作失败")
            else:
                # 未到期，如果是禁用状态则解禁
                if emby_info.lv == 'c':
                    if await emby.emby_change_policy(id=emby_info.embyid, method=False):
                        if sql_update_emby(Emby.tg == user.tg, lv='b', ex=emby_ex):
                            text = f'【订阅同步】\n#id{user.tg} 解封账户 [{emby_info.name}](tg://user?id={user.tg})\n' \
                                f'订阅有效期至: {emby_ex.strftime("%Y-%m-%d %H:%M:%S")}'
                            LOGGER.info(text)
                            try:
                                await bot.send_message(user.tg, text)
                            except FloodWait as f:
                                LOGGER.warning(str(f))
                                await sleep(f.value * 1.2)
                                await bot.send_message(user.tg, text)
                            except Exception as e:
                                LOGGER.error(e)
                        else:
                            LOGGER.warning(f"✈️ 用户 {user.tg} 解禁状态更新失败")
                    else:
                        LOGGER.error(f"✈️ 用户 {user.tg} Emby API解禁操作失败")
                else:
                    # 正常状态，只更新到期时间
                    if sql_update_emby(Emby.tg == user.tg, ex=emby_ex):
                        LOGGER.info(
                            f"✈️ 已更新用户 {user.tg} 的到期时间为 {emby_ex.strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        LOGGER.error(f"✈️ 更新用户 {user.tg} 的到期时间失败")
                renew_count += 1

        # 处理未绑定订阅的账号
        LOGGER.info("✈️ 开始处理未绑定订阅的账号...")
        unbound_ban_count = 0
        
        # 获取所有Emby账户
        all_emby_accounts = get_all_emby(Emby.embyid != None)
        if all_emby_accounts:
            for emby_account in all_emby_accounts:
                # 检查是否有对应的代理用户，以及是否绑定了订阅
                proxy_user = tg_to_proxy_user.get(emby_account.tg)
                
                # 如果没有代理用户记录，或者代理用户未绑定订阅，且账号状态是(b) 正常状态
                if (not proxy_user or not proxy_user.is_bound) and emby_account.lv == 'b' and emby_account.embyid:
                    # 禁用账户
                    if await emby.emby_change_policy(emby_account.embyid, method=True):
                        if sql_update_emby(Emby.tg == emby_account.tg, lv='c'):
                            text = f'【订阅同步】\n#id{emby_account.tg} 未绑定订阅禁用 [{emby_account.name}](tg://user?id={emby_account.tg})\n请绑定有效订阅以继续使用我们的服务'
                            LOGGER.info(text)
                            try:
                                send = await bot.send_message(emby_account.tg, text)
                                # await send.forward(chat_id)
                            except FloodWait as f:
                                LOGGER.warning(str(f))
                                await sleep(f.value * 1.2)
                                send = await bot.send_message(emby_account.tg, text)
                                # await send.forward(chat_id)
                            except Exception as e:
                                LOGGER.error(e)
                            unbound_ban_count += 1
                        else:
                            LOGGER.warning(f"✈️ 用户 {emby_account.tg} 禁用状态更新失败")
                    else:
                        LOGGER.error(f"✈️ 用户 {emby_account.tg} Emby API禁用操作失败")

        text = f"✈️ 订阅到期时间同步完成，共更新 {renew_count} 个用户，删除 {del_count} 个用户，禁用 {ban_count} 个用户，未绑定订阅禁用 {unbound_ban_count} 个用户"
        LOGGER.info(text)
        return text
    except Exception as e:
        text = f"✈️ 同步订阅到期时间时出错: {str(e)}"
        LOGGER.error(text)
        return text
