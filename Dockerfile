# ベースイメージとして公式のPythonイメージを使用
FROM python:3.11

# 作業ディレクトリを設定
WORKDIR /app

# 最初に依存関係ファイルのみをコピーしてインストール
# これにより、ソースコードの変更時にもライブラリの再インストールが不要になる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# botのソースコードを作業ディレクトリにコピー
COPY discord_bot.py .

# botを起動
CMD ["python", "discord_bot.py"]