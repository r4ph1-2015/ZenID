import zenid

# 1. Embed an image watermark programmatically
zenid.embed_image(
    input_path="input/input.jpg",
    output_path="output/watermarked.jpg",
    key="randomkey",
    author="Pixeldaguy"
)

# 2. Verify an image watermark programmatically
result = zenid.detect_image(
    image_path="output/watermarked.jpg",
    key="randomkey"
)

print(result)