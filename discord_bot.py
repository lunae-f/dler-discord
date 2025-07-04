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
# API接続用の内部URL
DLER_API_BASE_URL = os.environ.get("DLER_API_BASE_URL")
# Discord表示用の外部URL (未設定ならAPI用と同じURLを使う)
DLER_DISPLAY_URL = os.environ.get("DLER_DISPLAY_URL", DLER_API_BASE_URL)


# --- View定義 ---

# ActionView: ダウンロード完了後のボタン
class ActionView(discord.ui.View):
    def __init__(self, task_id: str, download_url: str, original_url: str, *, timeout=3600): # 60分タイムアウト
        super().__init__(timeout=timeout)
        self.task_id = task_id
        self.message = None

        self.add_item(discord.ui.Button(label="ダウンロード", style=discord.ButtonStyle.success, emoji="📥", url=download_url))
        self.add_item(discord.ui.Button(label="元動画", style=discord.ButtonStyle.secondary, emoji="🔗", url=original_url))

    async def on_timeout(self):
        if self.message:
            logger.info(f"ボタンがタイムアウトしました。自動削除を開始します: task_id={self.task_id}")
            for item in self.children:
                item.disabled = True
            timeout_embed = self.message.embeds[0]
            timeout_embed.title = "⌛ 自動削除中..."
            timeout_embed.description = "タイムアウトしたため、サーバーからファイルを自動的に削除しています。"
            timeout_embed.color = discord.Color.orange()
            await self.message.edit(embed=timeout_embed, view=self)

            try:
                requests.delete(f"{DLER_API_BASE_URL}/tasks/{self.task_id}").raise_for_status()
                logger.info(f"タイムアウトによる自動削除成功: task_id={self.task_id}")
                final_embed = self.message.embeds[0]
                final_embed.title = "🗑️ 自動削除完了"
                final_embed.description = "タイムアウトしたため、ファイルはサーバーから正常に削除されました。"
                final_embed.color = discord.Color.default()
                await self.message.edit(embed=final_embed, view=None)
            except requests.exceptions.RequestException as e:
                logger.error(f"タイムアウトによる自動削除中にエラーが発生: task_id={self.task_id}, エラー: {e}", exc_info=True)
                fail_embed = self.message.embeds[0]
                fail_embed.title = "❌ 自動削除失敗"
                fail_embed.description = "タイムアウトによる自動削除中にエラーが発生しました。"
                fail_embed.color = discord.Color.red()
                await self.message.edit(embed=fail_embed, view=self)


# FormatSelectionView: 形式選択ボタン
class FormatSelectionView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=300) # 5分タイムアウト
        self.url = url

    async def start_download(self, interaction: discord.Interaction, audio_only: bool):
        for item in self.children:
            item.disabled = True
        
        format_text = "音声" if audio_only else "動画"
        await interaction.response.edit_message(content=f"「{format_text}」を選択しました。ダウンロードを開始します...", view=self)
        
        await run_download_task(interaction, self.url, audio_only=audio_only)

    @discord.ui.button(label="動画", style=discord.ButtonStyle.primary, emoji="🎬")
    async def video_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.start_download(interaction, audio_only=False)

    @discord.ui.button(label="音声", style=discord.ButtonStyle.secondary, emoji="🎵")
    async def audio_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.start_download(interaction, audio_only=True)


# --- Botのロジック ---

async def run_download_task(interaction: discord.Interaction, url: str, audio_only: bool):
    """APIを呼び出してダウンロードタスクを実行し、状態をポーリングする"""
    
    try:
        logger.info(f"DLerにタスク作成リクエストを送信: {url}, audio_only={audio_only}")
        response = requests.post(
            f"{DLER_API_BASE_URL}/tasks",
            json={"url": url, "audio_only": audio_only}
        )
        response.raise_for_status()
        task_data = response.json()
        task_id = task_data.get("task_id")

        if not task_id:
            logger.error("タスク作成レスポンスにtask_idが含まれていません。")
            await interaction.edit_original_response(content="エラー: タスクIDの取得に失敗しました。", view=None)
            return
        logger.info(f"タスク作成成功: task_id={task_id}")

    except requests.exceptions.RequestException as e:
        logger.error(f"DLer APIへの接続に失敗しました: {e}", exc_info=True)
        await interaction.edit_original_response(content=f"エラー: DLer APIへの接続に失敗しました。\n`{e}`", view=None)
        return

    embed = discord.Embed(
        title="⌛ ダウンロード処理中...",
        description="ダウンロードを開始しました。\n完了までしばらくお待ちください。",
        color=discord.Color.blue()
    )
    embed.add_field(name="対象URL", value=url, inline=False)
    embed.set_footer(text=f"タスクID: {task_id}")
    await interaction.edit_original_response(content="", embed=embed, view=None)

    while True:
        try:
            await asyncio.sleep(3)
            logger.info(f"タスク状態を確認中: task_id={task_id}")
            status_response = requests.get(f"{DLER_API_BASE_URL}/tasks/{task_id}")
            status_response.raise_for_status()
            status_data = status_response.json()
            task_status = status_data.get("status")
            logger.info(f"タスク状態: {task_status}, task_id={task_id}")

            if task_status == "SUCCESS":
                download_url_path = status_data.get("download_url")
                
                # === ここで表示用URLを使うように変更 ===
                full_download_url = f"{DLER_DISPLAY_URL}{download_url_path}"
                
                original_filename = status_data.get("details", {}).get("original_filename", "file")
                
                logger.info(f"タスク成功: task_id={task_id}, ファイル名: {original_filename}")

                success_embed = discord.Embed(
                    title="✅ ダウンロード準備完了",
                    description=f"ファイル名: `{original_filename}`",
                    color=discord.Color.green()
                )
                success_embed.set_footer(text=f"タスクID: {task_id}")
                
                view = ActionView(task_id=task_id, download_url=full_download_url, original_url=url)
                message = await interaction.edit_original_response(embed=success_embed, view=view)
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
                await interaction.edit_original_response(embed=fail_embed, view=None)
                break

        except requests.exceptions.RequestException as e:
            logger.error(f"タスク状態の取得中にエラーが発生しました: task_id={task_id}, エラー: {e}", exc_info=True)
            await interaction.edit_original_response(content=f"エラー: タスク状態の取得中にエラーが発生しました。\n`{e}`", view=None)
            break


# --- Discord Bot コマンド ---
intents = discord.Intents.default()
bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"{bot.user} としてログインしました")
    logger.info(f"API接続用URL: {DLER_API_BASE_URL}")
    logger.info(f"Discord表示用URL: {DLER_DISPLAY_URL}")

@bot.slash_command(name="dler", description="URLを指定して動画または音声をダウンロードします。")
async def dler_command(ctx: discord.ApplicationContext, url: str):
    logger.info(f"コマンド受信: /dler, URL: {url}, サーバー: {ctx.guild.name}, ユーザー: {ctx.author.name}")
    
    embed = discord.Embed(
        title="ダウンロード形式の選択",
        description="ダウンロードする形式を選択してください。",
        color=discord.Color.blurple()
    )
    embed.add_field(name="対象URL", value=url)
    
    view = FormatSelectionView(url=url)
    await ctx.respond(embed=embed, view=view, ephemeral=True)


# --- Botの実行 ---
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN or not DLER_API_BASE_URL:
        logger.critical("環境変数 `DISCORD_BOT_TOKEN` または `DLER_API_BASE_URL` が設定されていません。")
    else:
        bot.run(DISCORD_BOT_TOKEN)