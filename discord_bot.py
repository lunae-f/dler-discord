import discord
import requests
import asyncio
import os
import logging

# --- ログ設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# --- 設定 ---
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
DLER_API_BASE_URL = os.environ.get("DLER_API_BASE_URL", "http://localhost:8000")

# --- Discord botの初期化 ---
intents = discord.Intents.default()
bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    """botが起動したときに呼び出される関数"""
    logger.info(f"{bot.user} としてログインしました")
    logger.info(f"DLer APIのエンドポイント: {DLER_API_BASE_URL}")

@bot.slash_command(name="dler", description="DLer APIを使って動画をダウンロードします。")
async def dler_command(ctx: discord.ApplicationContext, url: str):
    """/dlerコマンドを処理する関数"""
    logger.info(f"コマンド受信: /dler, URL: {url}, サーバー: {ctx.guild.name}, ユーザー: {ctx.author.name}")
    await ctx.respond(f"動画URLの処理を開始します: {url}")

    # 1. DLer APIにダウンロードタスクを作成する
    try:
        logger.info(f"DLerにタスク作成リクエストを送信: {url}")
        create_task_response = requests.post(
            f"{DLER_API_BASE_URL}/tasks",
            json={"url": url}
        )
        create_task_response.raise_for_status()
        task_data = create_task_response.json()
        task_id = task_data.get("task_id")

        if not task_id:
            logger.error("タスク作成レスポンスにtask_idが含まれていません。")
            await ctx.edit(content="エラー: タスクIDの取得に失敗しました。")
            return
        
        logger.info(f"タスク作成成功: task_id={task_id}")

    except requests.exceptions.RequestException as e:
        logger.error(f"DLer APIへの接続に失敗しました: {e}", exc_info=True)
        await ctx.edit(content=f"エラー: DLer APIへの接続に失敗しました。\n`{e}`")
        return

    await ctx.edit(content=f"ダウンロードタスクを作成しました (タスクID: {task_id})。完了までお待ちください...")

    # 2. タスクの状態を定期的に確認する (ポーリング)
    while True:
        try:
            logger.info(f"タスク状態を確認中: task_id={task_id}")
            status_response = requests.get(f"{DLER_API_BASE_URL}/tasks/{task_id}")
            status_response.raise_for_status()
            status_data = status_response.json()
            task_status = status_data.get("status")
            logger.info(f"タスク状態: {task_status}, task_id={task_id}")

            if task_status == "SUCCESS":
                download_url_path = status_data.get("download_url")
                full_download_url = f"{DLER_API_BASE_URL}{download_url_path}"
                original_filename = status_data.get("details", {}).get("original_filename", "video.mp4")
                
                logger.info(f"タスク成功: task_id={task_id}, ファイル名: {original_filename}")
                embed = discord.Embed(title="✅ ダウンロード準備完了", description=f"ファイル名: `{original_filename}`", color=discord.Color.green())
                embed.add_field(name="ダウンロードURL", value=full_download_url, inline=False)
                await ctx.edit(content="", embed=embed)
                break

            elif task_status == "FAILURE":
                error_details = status_data.get("details", "不明なエラー")
                logger.error(f"タスク失敗: task_id={task_id}, 理由: {error_details}")
                await ctx.edit(content=f"❌ ダウンロードに失敗しました。\n理由: `{error_details}`")
                break

            # 3秒待ってから再度確認
            await asyncio.sleep(3)

        except requests.exceptions.RequestException as e:
            logger.error(f"タスク状態の取得中にエラーが発生しました: task_id={task_id}, エラー: {e}", exc_info=True)
            await ctx.edit(content=f"エラー: タスク状態の取得中にエラーが発生しました。\n`{e}`")
            break

# --- botの実行 ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        logger.critical("環境変数 `DISCORD_BOT_TOKEN` が設定されていません。")
    else:
        bot.run(DISCORD_BOT_TOKEN)