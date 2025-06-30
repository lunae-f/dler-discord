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


# --- 削除ボタンのView ---
class DeletionView(discord.ui.View):
    def __init__(self, task_id: str, *, timeout=300): # タイムアウトを5分に設定
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.message = None # 後でメッセージオブジェクトを格納

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # ボタンを無効化し、ユーザーに処理中であることを示す
        button.disabled = True
        button.label = "削除中..."
        await interaction.response.edit_message(view=self)

        logger.info(f"削除ボタンがクリックされました: task_id={self.task_id}, ユーザー: {interaction.user.name}")

        try:
            # dler APIにDELETEリクエストを送信
            response = requests.delete(f"{DLER_API_BASE_URL}/tasks/{self.task_id}")
            response.raise_for_status()  # エラーがあれば例外を発生

            logger.info(f"タスク削除成功: task_id={self.task_id}")

            # 元のメッセージを編集して削除完了を通知
            new_embed = interaction.message.embeds[0]
            new_embed.title = "🗑️ 削除完了"
            new_embed.description = f"ファイルはサーバーから正常に削除されました。"
            new_embed.color = discord.Color.default()

            # ボタンをメッセージから削除
            await interaction.message.edit(embed=new_embed, view=None)

        except requests.exceptions.RequestException as e:
            logger.error(f"タスク削除中にエラーが発生: task_id={self.task_id}, エラー: {e}", exc_info=True)
            # エラーが発生したことをユーザーに通知
            button.label = "削除失敗"
            await interaction.followup.send(f"エラー: ファイルの削除に失敗しました。\n`{e}`", ephemeral=True)
            # viewを更新してボタンの状態を反映
            await interaction.message.edit(view=self)

    async def on_timeout(self):
        # タイムアウトしたらボタンを無効化
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)
            logger.info(f"削除ボタンがタイムアウトしました: task_id={self.task_id}")


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

    # Embedを作成して処理中のUIを表示
    embed = discord.Embed(
        title="⌛ ダウンロード処理中...",
        description=f"動画のダウンロードを開始しました。\n完了までしばらくお待ちください。",
        color=discord.Color.blue()
    )
    embed.add_field(name="対象URL", value=url, inline=False)
    embed.set_footer(text=f"タスクID: {task_id}")

    await ctx.edit(content="", embed=embed)

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

                embed = discord.Embed(
                    title="✅ ダウンロード準備完了",
                    description=f"ファイル名: `{original_filename}`",
                    color=discord.Color.green()
                )
                embed.add_field(name="ダウンロードURL", value=full_download_url, inline=False)
                embed.set_footer(text=f"タスクID: {task_id}")

                view = DeletionView(task_id=task_id)
                message = await ctx.edit(content="", embed=embed, view=view)
                view.message = message
                break

            elif task_status == "FAILURE":
                error_details = status_data.get("details", "不明なエラー")
                logger.error(f"タスク失敗: task_id={task_id}, 理由: {error_details}")

                # 失敗時のEmbedを作成
                fail_embed = discord.Embed(
                    title="❌ ダウンロード失敗",
                    description=f"理由: `{error_details}`",
                    color=discord.Color.red()
                )
                fail_embed.add_field(name="対象URL", value=url, inline=False)
                fail_embed.set_footer(text=f"タスクID: {task_id}")
                await ctx.edit(embed=fail_embed)
                break

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