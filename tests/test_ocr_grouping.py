from app.ocr import group_rows


def box(x, y, w=80, h=20):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def test_boxes_on_same_row_are_merged_left_to_right():
    results = [
        (box(200, 102), "100g", 0.9),
        (box(10, 100), "Net Wt.", 0.8),
        (box(10, 160), "MRP Rs. 45", 0.7),
    ]
    lines = group_rows(results)
    assert [l.text for l in lines] == ["Net Wt. 100g", "MRP Rs. 45"]
    assert lines[0].conf == 0.85


def test_empty_text_is_dropped():
    assert group_rows([(box(0, 0), "  ", 0.9)]) == []


def test_columns_are_read_one_after_another():
    from app.ocr import group_columns
    R = [(box(10, 10, 300), "Plot No. 267, Industrial Area,", .9), (box(500, 10, 200), "140 Pages MRP: Rs 60.00", .9),
         (box(10, 40, 300), "Harohalli - 562112,", .9), (box(500, 40, 200), "(Incl. of Taxes)", .9)]
    assert [l.text for l in group_columns(R)] == ["Plot No. 267, Industrial Area,", "Harohalli - 562112,",
                                                  "140 Pages MRP: Rs 60.00", "(Incl. of Taxes)"]
    assert [l.text for l in group_columns([(box(10, 10, 300), "Net Wt.", .9), (box(100, 12, 100), "100g", .9)])] == ["Net Wt. 100g"]
