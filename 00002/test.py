# type: ignore
# pylint: disable=all
import cv2 as cv
import numpy as np

filename = "data/97C3MPJ.png"
img = cv.imread(cv.samples.findFile(filename))
cImage = np.copy(img)  # image to draw lines
cv.imshow("image", img)  # name the window as "image"
cv.waitKey(0)
cv.destroyWindow("image")  # close the window

gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
cv.imshow("gray", gray)
cv.waitKey(0)
cv.destroyWindow("gray")
canny = cv.Canny(gray, 50, 150)
cv.imshow("canny", canny)
cv.waitKey(0)
cv.destroyWindow("canny")

# cv.HoughLinesP(image, rho, theta, threshold[, lines[, minLineLength[, maxLineGap]]]) → lines
rho = 1
theta = np.pi / 180
threshold = 50
minLinLength = 350
maxLineGap = 6
linesP = cv.HoughLinesP(
    canny, rho, theta, threshold, None, minLinLength, maxLineGap
)


def is_vertical(line):
    return line[0] == line[2]


def is_horizontal(line):
    return line[1] == line[3]


def overlapping_filter(lines, sorting_index):
    filtered_lines = []

    lines = sorted(lines, key=lambda lines: lines[sorting_index])
    separation = 5
    for i in range(len(lines)):
        l_curr = lines[i]
        if i > 0:
            l_prev = lines[i - 1]
            if (l_curr[sorting_index] - l_prev[sorting_index]) > separation:
                filtered_lines.append(l_curr)
        else:
            filtered_lines.append(l_curr)

    return filtered_lines


horizontal_lines = []
vertical_lines = []

if linesP is not None:
    for i in range(0, len(linesP)):
        l = linesP[i][0]
        if is_vertical(l):
            vertical_lines.append(l)

        elif is_horizontal(l):
            horizontal_lines.append(l)
    horizontal_lines = overlapping_filter(horizontal_lines, 1)
    vertical_lines = overlapping_filter(vertical_lines, 0)
    for i, line in enumerate(horizontal_lines):
        cv.line(
            cImage,
            (line[0], line[1]),
            (line[2], line[3]),
            (0, 255, 0),
            3,
            cv.LINE_AA,
        )
        cv.putText(
            cImage,
            str(i) + "h",
            (line[0] + 5, line[1]),
            cv.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv.LINE_AA,
        )

    for i, line in enumerate(vertical_lines):
        cv.line(
            cImage,
            (line[0], line[1]),
            (line[2], line[3]),
            (0, 0, 255),
            3,
            cv.LINE_AA,
        )
        cv.putText(
            cImage,
            str(i) + "v",
            (line[0], line[1] + 5),
            cv.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv.LINE_AA,
        )

cv.imshow("with_line", cImage)
cv.waitKey(0)
cv.destroyWindow("with_line")  # close the window
