#!/bin/bash
# Script dọn dẹp các thư mục log (conversation) cũ của Antigravity CLI
# Xóa các thư mục cũ hơn 1 ngày (24 giờ)

BRAIN_DIR="$HOME/.gemini/antigravity-cli/brain"

if [ -d "$BRAIN_DIR" ]; then
    echo "Đang dọn dẹp các log cũ hơn 24 giờ trong $BRAIN_DIR..."
    # Tìm và xóa các thư mục trong brain cũ hơn 1 ngày (+1440 phút)
    find "$BRAIN_DIR" -mindepth 1 -maxdepth 1 -type d -mmin +1440 -exec rm -rf {} +
    echo "Dọn dẹp hoàn tất!"
else
    echo "Thư mục $BRAIN_DIR không tồn tại."
fi
