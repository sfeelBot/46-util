#바코드to 셀넘버.ipynb
import os
import re
import shutil

# =========================
# 1. 매핑 데이터
# =========================
mapping_raw = """
83 Test_2025_01_16_7780
84 Test_2025_01_16_7779
254 Test_2025_01_16_7777
81 Test_2025_01_16_7782
85 Test_2025_01_16_7768
86 Test_2025_01_16_7769
88 Test_2025_01_16_7771
260 Test_2025_01_16_7774
173 Test_2025_01_16_7515
174 Test_2025_01_16_7514
256 Test_2025_01_16_7511
92 Test_2025_01_16_7762
93 Test_2025_01_16_7763
96 Test_2025_01_16_7766
94 Test_2025_01_16_7764
100 Test_2025_01_16_7754
102 Test_2025_01_16_7756
104 Test_2025_01_16_7758
99 Test_2025_01_16_7753
165 Test_2025_01_16_7523
167 Test_2025_01_16_7521
169 Test_2025_01_16_7519
162 Test_2025_01_16_7526
63 Test_2025_01_16_7749
245 Test_2025_01_16_7748
246 Test_2025_01_16_7744
59 Test_2025_01_16_7745
51 Test_2025_01_16_7736
53 Test_2025_01_16_7743
249 Test_2025_01_16_7740
54 Test_2025_01_16_7741
158 Test_2025_01_16_7533
159 Test_2025_01_16_7532
160 Test_2025_01_16_7531
161 Test_2025_01_16_7530
45 Test_2025_01_16_7729
46 Test_2025_01_16_7730
47 Test_2025_01_16_7728
41 Test_2025_01_16_7735
32 Test_2025_01_16_7720
33 Test_2025_01_16_7721
36 Test_2025_01_16_7726
34 Test_2025_01_16_7722
149 Test_2025_01_16_7542
151 Test_2025_01_16_7535
152 Test_2025_01_16_7540
154 Test_2025_01_16_7538
56 Test_2025_01_16_7710
57 Test_2025_01_16_7716
58 Test_2025_01_16_7709
119 Test_2025_01_16_7712
48 Test_2025_01_16_7711
49 Test_2025_01_16_7707
207 Test_2025_01_16_7614
210 Test_2025_01_16_7607
201 Test_2025_01_16_7613
202 Test_2025_01_16_7612
203 Test_2025_01_16_7611
143 Test_2025_01_16_7553
109 Test_2025_01_16_7548
120 Test_2025_01_16_7550
141 Test_2025_01_16_7552
198 Test_2025_01_16_7629
199 Test_2025_01_16_7631
200 Test_2025_01_16_7627
175 Test_2025_01_16_7638
176 Test_2025_01_16_7640
177 Test_2025_01_16_7637
193 Test_2025_01_16_7615
222 Test_2025_01_16_7622
223 Test_2025_01_16_7621
187 Test_2025_01_16_7619
188 Test_2025_01_16_7625
189 Test_2025_01_16_7618
128 Test_2025_01_16_7568
135 Test_2025_01_16_7561
140 Test_2025_01_16_7556
129 Test_2025_01_16_7567
130 Test_2025_01_16_7566
131 Test_2025_01_16_7565
2 Test_2025_01_16_7705
3 Test_2025_01_16_7702
5 Test_2025_01_16_7700
11 Test_2025_01_16_7694
12 Test_2025_01_16_7691
13 Test_2025_01_16_7697
15 Test_2025_01_16_7689
112 Test_2025_01_16_7688
17 Test_2025_01_16_7685
16 Test_2025_01_16_7686
18 Test_2025_01_16_7683
19 Test_2025_01_16_7684
185 Test_2025_01_16_7588
186 Test_2025_01_16_7589
224 Test_2025_01_16_7591
225 Test_2025_01_16_7584
226 Test_2025_01_16_7587
227 Test_2025_01_16_7586
183 Test_2025_01_16_7594
184 Test_2025_01_16_7602
211 Test_2025_01_16_7596
213 Test_2025_01_16_7598
214 Test_2025_01_16_7592
215 Test_2025_01_16_7599
26 Test_2025_01_16_7673
28 Test_2025_01_16_7670
31 Test_2025_01_16_7668
24 Test_2025_01_16_7674
25 Test_2025_01_16_7672
27 Test_2025_01_16_7671
"""

# =========================
# 2. 매핑 생성
# =========================
barcode_to_cell = {}
for line in mapping_raw.strip().split("\n"):
    parts = line.split()
    if len(parts) < 2:
        continue
    barcode = parts[1].split("_")[-1]
    barcode_to_cell[barcode] = parts[0]

# =========================
# 3. 경로 설정
# =========================
source_root = r"D:\AI검사개발그룹_과제\과제_46X-RAY 이물검사\Series Line 양산 설비 제작\Tilt train\B열 이물 Cell\BMP"
target_folder = r"D:\renamed_images_B"
os.makedirs(target_folder, exist_ok=True)

# =========================
# 4. 실행 가드
# =========================
guard_file = os.path.join(target_folder, "RUN_DONE.flag")
if os.path.exists(guard_file):
    print("⚠️ 이미 실행된 작업입니다. 종료합니다.")
    raise SystemExit

# =========================
# 5. 원본 BMP 개수 계산
# =========================
source_bmp_count = 0
for root, _, files in os.walk(source_root):
    if os.path.abspath(root).startswith(os.path.abspath(target_folder)):
        continue
    source_bmp_count += sum(1 for f in files if f.lower().endswith(".bmp"))

print(f"📂 원본 BMP 파일 개수: {source_bmp_count}")

# =========================
# 6. 파일 처리
# =========================
created_files = 0

for root, _, files in os.walk(source_root):
    if os.path.abspath(root).startswith(os.path.abspath(target_folder)):
        continue

    for filename in files:
        if not filename.lower().endswith(".bmp"):
            continue
        if re.match(r"^\d+_", filename):
            continue

        match = re.search(r"\d{4}-\d{2}-\d{2}-(\d+)-", filename)
        if not match:
            continue

        barcode = match.group(1)
        if barcode not in barcode_to_cell:
            continue

        cell = barcode_to_cell[barcode]
        new_filename = f"{cell}_{filename}"
        target_path = os.path.join(target_folder, new_filename)

        base, ext = os.path.splitext(new_filename)
        i = 1
        while os.path.exists(target_path):
            target_path = os.path.join(target_folder, f"{base}_{i}{ext}")
            i += 1

        shutil.copy2(os.path.join(root, filename), target_path)
        created_files += 1

# =========================
# 7. 결과 개수 검증
# =========================
target_bmp_count = sum(
    1 for f in os.listdir(target_folder) if f.lower().endswith(".bmp")
)

print(f"📁 생성된 BMP 파일 개수: {target_bmp_count}")

# =========================
# 8. 검증 결과 처리
# =========================
if source_bmp_count == target_bmp_count == created_files:
    with open(guard_file, "w", encoding="utf-8") as f:
        f.write("DONE")
    print("✅ 파일 개수 검증 성공 — 작업 완료")
else:
    print("❌ 파일 개수 불일치!")
    print(f"   원본: {source_bmp_count}")
    print(f"   생성됨: {created_files}")
    print(f"   결과폴더: {target_bmp_count}")
    print("⚠️ RUN_DONE.flag 생성 안 됨 (재실행 필요)")

