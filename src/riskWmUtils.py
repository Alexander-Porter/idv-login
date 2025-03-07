from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

def wm(image_bytes,text):
    image = Image.open(BytesIO(image_bytes)).convert("RGBA")
    

    watermark = Image.new("RGBA", image.size, (0, 0, 0, 0))
    
    font_size = max(20, image.size[0] // 15)
    
    try:
        font = ImageFont.truetype("msyh.ttc", font_size)
    except IOError:
        text='If you are not the owner of this device\n presenting this QR Code.\n Do NOT Scan! Do NOT Scan! Do NOT Scan!'
        font = ImageFont.load_default()
    
    draw = ImageDraw.Draw(watermark)
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (image.size[0] - text_width) // 2
    y = (image.size[1] - text_height) // 2
    

    draw.text((x, y), text, font=font, fill=(255, 0, 0, 128))
    watermarked = Image.alpha_composite(image, watermark)

    output = BytesIO()
    watermarked.save(output, format="PNG")
    
    return output.getvalue()
