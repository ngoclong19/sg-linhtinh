"""Recognize Steam key using Optical Character Recognition
"""
# import the necessary packages
import argparse

import cv2
import pytesseract
from cv2.typing import MatLike
from PIL import Image, ImageFilter

# import re

RESIZE_FACTOR = 3.2
# CROP_SIZE = 20


class ExtractedArgs:
    image: str


def main0():
    # construct the argument parser and parse the arguments
    ap: argparse.ArgumentParser = argparse.ArgumentParser()
    ap.add_argument("image", help="path to input image to be OCR'd")
    args: ExtractedArgs = ap.parse_args(namespace=ExtractedArgs())

    # load the input image
    image: Image.Image = Image.open(args.image).convert("RGB")  # 57

    image = image.convert("L")  # 34
    # image = image.crop((CROP_SIZE, CROP_SIZE, image.width, image.height))
    image = image.resize(
        (int(image.width * RESIZE_FACTOR), int(image.height * RESIZE_FACTOR)),
        Image.LANCZOS,
    )  # 10

    image = image.filter(ImageFilter.SMOOTH_MORE)  # 9
    # image = image.filter(ImageFilter.MinFilter(3))
    # image = image.filter(ImageFilter.UnsharpMask(6.8, 269, 0))  # 15
    # image = image.filter(ImageFilter.SHARPEN)  # 10

    # image.show()
    # image.save("image.png")

    # OCR the input image using Tesseract
    # options: str = "--dpi 300 --tessdata-dir ./tessdata tessconfigs"  # 15
    options: str = "--dpi 300 tessconfigs"
    text: str = pytesseract.image_to_string(image, config=options)
    print(text)
    # print("---")

    # text = text.replace("-+", "+")
    # pattern: re.Pattern[str] = re.compile(r".+=\w{5}-\w{5}\+F\d\d?\w{5}")
    # text = "\n".join([l for l in text.split("\n") if pattern.match(l)])
    # print(text)
    # print(len(text.split()))
    # cv2.imshow("aa", image)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()


def main():
    # construct the argument parser and parse the arguments
    ap: argparse.ArgumentParser = argparse.ArgumentParser()
    ap.add_argument("image", help="path to input image to be OCR'd")
    args: ExtractedArgs = ap.parse_args(namespace=ExtractedArgs())

    # load the input image
    image: MatLike = cv2.imread(args.image)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    image = image.convert("L")  # 34
    # image = image.crop((CROP_SIZE, CROP_SIZE, image.width, image.height))
    image = image.resize(
        (int(image.width * RESIZE_FACTOR), int(image.height * RESIZE_FACTOR)),
        Image.LANCZOS,
    )  # 10

    image = image.filter(ImageFilter.SMOOTH_MORE)  # 9
    # image = image.filter(ImageFilter.MinFilter(3))
    # image = image.filter(ImageFilter.UnsharpMask(6.8, 269, 0))  # 15
    # image = image.filter(ImageFilter.SHARPEN)  # 10

    # image.show()
    # image.save("image.png")

    # OCR the input image using Tesseract
    # options: str = "--dpi 300 --tessdata-dir ./tessdata tessconfigs"  # 15
    options: str = "--dpi 300 tessconfigs"
    text: str = pytesseract.image_to_string(image, config=options)
    print(text)
    # print("---")

    # text = text.replace("-+", "+")
    # pattern: re.Pattern[str] = re.compile(r".+=\w{5}-\w{5}\+F\d\d?\w{5}")
    # text = "\n".join([l for l in text.split("\n") if pattern.match(l)])
    # print(text)
    # print(len(text.split()))
    # cv2.imshow("aa", image)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
