
import asyncio
import re
from pathlib import Path
from getpass import getpass

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

# ==========================================
# 基本設定
# ==========================================

ANA_URL = "https://www.ana.co.jp/"
PROFILE_DIR = Path.home() / "ana_automation_profile"

DEPARTURE = "nrt"
ARRIVAL = "akl"


# ==========================================
# 表示中の要素をクリック
# ==========================================

async def click_visible(locator, description, timeout=15000):

    try:
        count = await locator.count()

        for i in range(count):
            item = locator.nth(i)

            if await item.is_visible():
                await item.click(timeout=timeout)
                print(f"成功：{description}")
                return True

    except PlaywrightError as error:
        print(f"クリック失敗：{description}")
        print(str(error)[:200])

    return False


# ==========================================
# 空港を選択
# ==========================================

async def select_airport(page, field_name, code, option_name):

    print(f"{field_name}を設定します。")

    field = page.get_by_role(
        "textbox",
        name=field_name,
        exact=True
    )

    await field.click(timeout=15000)
    await field.fill(code, timeout=15000)

    option = page.get_by_role(
        "option",
        name=re.compile(option_name, re.IGNORECASE)
    )

    await option.first.wait_for(
        state="visible",
        timeout=15000
    )

    await option.first.click(timeout=15000)

    print(f"設定完了：{field_name} = {code.upper()}")


# ==========================================
# 検索フォーム入力
# ==========================================

async def fill_search_form(page):

    print()
    print("===== 検索条件の自動入力 =====")

    # 往復・特典予約は既定の選択を利用

    # 出発地：成田
    await select_airport(
        page,
        "出発地",
        DEPARTURE,
        "東京.*成田"
    )

    # 到着地：オークランド
    await select_airport(
        page,
        "到着地",
        ARRIVAL,
        "オークランド"
    )

    # クラスは画面の既定値
    # 「特典エコノミー」を使用
    print("クラス：特典エコノミー（初期設定）")

    # 大人の人数を1名から2名へ
    # Codegenで記録した操作
    print("大人人数を2名に変更します。")

    plus_button = page.get_by_text("+", exact=True).first

    await plus_button.click(timeout=15000)

    print("大人の＋ボタンを1回クリックしました。")

    print()
    print("検索条件の自動入力が終了しました。")
    print("日付はブラウザで手動選択してください。")


# ==========================================
# メイン処理
# ==========================================

async def main():

    async with async_playwright() as p:

        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1280, "height": 900}
        )

        try:

            # ==================================
            # STEP 1：ANA公式サイト
            # ==================================

            page = (
                context.pages[0]
                if context.pages
                else await context.new_page()
            )

            print("ANAサイトを開きます。")

            await page.goto(
                ANA_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print("ANAサイトを開きました。")

            # ==================================
            # STEP 2：海外タブ
            # ==================================

            overseas = page.get_by_role(
                "tab",
                name=re.compile("海外")
            )

            if await overseas.count() > 0:
                await click_visible(
                    overseas,
                    "海外タブ"
                )

            # ==================================
            # STEP 3：特典航空券タブ
            # ==================================

            award_tab = page.get_by_role(
                "tab",
                name="特典航空券",
                exact=True
            )

            success = await click_visible(
                award_tab,
                "特典航空券タブ"
            )

            if not success:
                await asyncio.to_thread(
                    input,
                    "手動で特典航空券タブを選択しEnter："
                )

            # ==================================
            # STEP 4：予約ページへ移動
            # ==================================

            print("特典航空券予約リンクを探します。")

            reservation = page.get_by_role(
                "link",
                name=re.compile("特典航空券予約")
            )

            booking_page = None

            try:
                async with page.expect_popup(
                    timeout=15000
                ) as popup_info:

                    await reservation.first.click(
                        timeout=15000
                    )

                booking_page = await popup_info.value

                await booking_page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=30000
                )

                print("予約ページを開きました。")

            except PlaywrightError as error:

                print("予約ページへの自動移動に失敗しました。")
                print(str(error)[:250])

                await asyncio.to_thread(
                    input,
                    "手動で予約ページを開いてEnter："
                )

                tabs = [
                    tab for tab in context.pages
                    if tab != page and not tab.is_closed()
                ]

                booking_page = tabs[-1] if tabs else page

            # ==================================
            # STEP 5：ANAログイン
            # ==================================

            print()
            print("ログイン状態を確認します。")

            password_field = booking_page.locator(
                'input[type="password"]:visible'
            )

            try:
                await password_field.first.wait_for(
                    state="visible",
                    timeout=10000
                )

                if await password_field.count() == 1:

                    password = await asyncio.to_thread(
                        getpass,
                        "ANAパスワード："
                    )

                    try:
                        await password_field.first.fill(
                            password
                        )
                    finally:
                        del password

                    login_button = booking_page.get_by_role(
                        "button",
                        name="ログイン",
                        exact=True
                    )

                    if await login_button.count() == 1:
                        await login_button.click(
                            timeout=15000
                        )
                        print("ログインを実行しました。")
                    else:
                        print("ログインボタンを手動で押してください。")

            except PlaywrightTimeoutError:
                print("パスワード入力欄は表示されていません。")

            # ==================================
            # STEP 6：検索フォーム表示待ち
            # ==================================

            departure_field = booking_page.get_by_role(
                "textbox",
                name="出発地",
                exact=True
            )

            try:
                await departure_field.wait_for(
                    state="visible",
                    timeout=20000
                )

            except PlaywrightTimeoutError:
                print("検索画面を確認してください。")

                await asyncio.to_thread(
                    input,
                    "検索画面が表示されたらEnter："
                )

                await departure_field.wait_for(
                    state="visible",
                    timeout=15000
                )

            print("特典航空券検索画面を確認しました。")

            # ==================================
            # STEP 7：検索条件を自動入力
            # ==================================

            await fill_search_form(booking_page)

            # ==================================
            # STEP 8：手動で日付を選択
            # ==================================

            print()
            print("===== 現在の検索条件 =====")
            print("出発地：東京（成田）")
            print("到着地：オークランド")
            print("旅程：往復")
            print("クラス：特典エコノミー")
            print("大人：2名（画面で要確認）")
            print("日付：手動で選択")
            print()

            await asyncio.to_thread(
                input,
                "往路・復路の日付を選択したらEnter："
            )

            print()
            print("検索画面の入力が完了しました。")
            print("内容を確認してください。")

            # 検索ボタンは自動クリックしない
            await asyncio.to_thread(
                input,
                "終了する場合はEnter："
            )

        except PlaywrightError as error:

            print()
            print("Playwrightでエラーが発生しました。")
            print(str(error))

            await asyncio.to_thread(
                input,
                "画面を確認したらEnter："
            )

        finally:
            await context.close()

    print("プログラムを終了しました。")


if __name__ == "__main__":
    asyncio.run(main())
