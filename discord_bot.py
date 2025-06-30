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


# --- ボタンのView ---
class ActionView(discord.ui.View):
    # === タイムアウト時間を12時間(43200秒)に変更 ===
    def __init__(self, task_id: str, download_url: str, original_url: str, *, timeout=43200):
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.message = None

        # 1. ダウンロードボタン (リンク)
        self.add_item(discord.ui.Button(label="DL", style=discord.ButtonStyle.success, emoji="📥", url=download_url))
        
        # 2. 元動画ボタン (リンク)
        self.add_item(discord.ui.Button(label="元動画", style=discord.ButtonStyle.secondary, emoji="🔗", url=original_url))

        # 3. サーバーから削除ボタン
        delete_button = discord.ui.Button(label="削除", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="delete_button")
        delete_button.callback = self.delete_button_callback
        self.add_item(delete_button)

    # 削除ボタンのコールバック関数
    async def delete_button_callback(self, interaction: discord.Interaction):
        button = discord.utils.get(self.children, custom_id="delete_button")
        
        button.disabled = True
        button.label = "削除中..."
        await interaction.response.edit_message(view=self)

        logger.info(f"削除ボタンがクリックされました: task_id={self.task_id}, ユーザー: {interaction.user.name}")

        try:
            response = requests.delete(f"{DLER_API_BASE_URL}/tasks/{self.task_id}")
            response.raise_for_status()

            logger.info(f"タスク削除成功: task_id={self.task_id}")

            new_embed = interaction.message.embeds[0]
            new_embed.title = "🗑️ 削除完了"
            new_embed.description = f"ファイルはサーバーから正常に削除されました。"
            new_embed.color = discord.Color.default()
            
            await interaction.message.edit(embed=new_embed, view=None)

        except requests.exceptions.RequestException as e:
            logger.error(f"タスク削除中にエラーが発生: task_id={self.task_id}, エラー: {e}", exc_info=True)
            button.label = "削除失敗"
            await interaction.followup.send(f"エラー: ファイルの削除に失敗しました。\n`{e}`", ephemeral=True)
            await interaction.message.edit(view=self)

    # === タイムアウト時の処理を修正 ===
    async def on_timeout(self):
        if self.message:
            logger.info(f"ボタンがタイムアウトしました。自動削除を開始します: task_id={self.task_id}")
            
            # 全てのボタンを無効化
            for item in self.children:
                item.disabled = True
            
            # メッセージを「自動削除中...」に更新
            timeout_embed = self.message.embeds[0]
            timeout_embed.title = "⌛ 自動削除中..."
            timeout_embed.description = "タイムアウトしたため、サーバーからファイルを自動的に削除しています。"
            timeout_embed.color = discord.Color.orange()
            await self.message.edit(embed=timeout_embed, view=self)

            try:
                # dler APIにDELETEリクエストを送信
                response = requests.delete(f"{DLER_API_BASE_URL}/tasks/{self.task_id}")
                response.raise_for_status()

                logger.info(f"タイムアウトによる自動削除成功: task_id={self.task_id}")

                # 元のメッセージを編集して削除完了を通知
                final_embed = self.message.embeds[0]
                final_embed.title = "🗑️ 自動削除完了"
                final_embed.description = f"タイムアウトしたため、ファイルはサーバーから正常に削除されました。"
                final_embed.color = discord.Color.default()

                # ボタンをメッセージから削除
                await self.message.edit(embed=final_embed, view=None)

            except requests.exceptions.RequestException as e:
                logger.error(f"タイムアウトによる自動削除中にエラーが発生: task_id={self.task_id}, エラー: {e}", exc_info=True)
                # エラーが発生したことを通知
                fail_embed = self.message.embeds[0]
                fail_embed.title = "❌ 自動削除失敗"
                fail_embed.description = f"タイムアウトによる自動削除中にエラーが発生しました。"
                fail_embed.color = discord.Color.red()
                await self.message.edit(embed=fail_embed, view=self)

# --- Discord botの初期化 ---
intents = discord.Intents.default()
bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"{bot.user} としてログインしました")
    logger.info(f"DLer APIのエンドポイント: {DLER_API_BASE_URL}")

@bot.slash_command(name="dler", description="DLer APIを使って動画をダウンロードします。")
async def dler_command(ctx: discord.ApplicationContext, url: str):
    logger.info(f"コマンド受信: /dler, URL: {url}, サーバー: {ctx.guild.name}, ユーザー: {ctx.author.name}")
    interaction = await ctx.respond("処理を開始します...", ephemeral=False)

    try:
        logger.info(f"DLerにタスク作成リクエストを送信: {url}")
        create_task_response = requests.post(f"{DLER_API_BASE_URL}/tasks", json={"url": url})
        create_task_response.raise_for_status()
        task_data = create_task_response.json()
        task_id = task_data.get("task_id")

        if not task_id:
            logger.error("タスク作成レスポンスにtask_idが含まれていません。")
            await interaction.edit_original_response(content="エラー: タスクIDの取得に失敗しました。")
            return
        
        logger.info(f"タスク作成成功: task_id={task_id}")

    except requests.exceptions.RequestException as e:
        logger.error(f"DLer APIへの接続に失敗しました: {e}", exc_info=True)
        await interaction.edit_original_response(content=f"エラー: DLer APIへの接続に失敗しました。\n`{e}`")
        return

    embed = discord.Embed(
        title="⌛ ダウンロード処理中...",
        description="動画のダウンロードを開始しました。\n完了までしばらくお待ちください。",
        color=discord.Color.blue()
    )
    embed.add_field(name="対象URL", value=url, inline=False)
    embed.set_footer(text=f"タスクID: {task_id}")
    await interaction.edit_original_response(content="", embed=embed)

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
                embed.set_footer(text=f"タスクID: {task_id}")

                view = ActionView(task_id=task_id, download_url=full_download_url, original_url=url)
                message = await interaction.edit_original_response(content="", embed=embed, view=view)
                view.message = message
                break

            elif task_status == "FAILURE":
                error_details = status_data.get("details", "不明なエラー")
                logger.error(f"タスク失敗: task_id={task_id}, 理由: {error_details}")

                fail_embed = discord.Embed(
                    title="❌ ダウンロード失敗",
                    description=f"理由: `{error_details}`",
                    color=discord.Color.red()
                )
                fail_embed.add_field(name="対象URL", value=url, inline=False)
                fail_embed.set_footer(text=f"タスクID: {task_id}")
                await interaction.edit_original_response(embed=fail_embed)
                break

            await asyncio.sleep(3)

        except requests.exceptions.RequestException as e:
            logger.error(f"タスク状態の取得中にエラーが発生しました: task_id={task_id}, エラー: {e}", exc_info=True)
            await interaction.edit_original_response(content=f"エラー: タスク状態の取得中にエラーが発生しました。\n`{e}`")
            break

# --- botの実行 ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        logger.critical("環境変数 `DISCORD_BOT_TOKEN` が設定されていません。")
    else:
        bot.run(DISCORD_BOT_TOKEN)