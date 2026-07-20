# -*- coding: utf-8 -*-
import io

TEMPLATE = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\dashboard_template.html"
DATA_JSON = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\dashboard_data.json"
OUT = r"C:\Users\hshbo\OneDrive\바탕 화면\코딩\scm_dashboard.html"

with io.open(TEMPLATE, "r", encoding="utf-8") as f:
    template = f.read()
with io.open(DATA_JSON, "r", encoding="utf-8") as f:
    data_json = f.read()

# </script> 문자열이 JSON 내부(문자열 값)에 등장할 경우를 대비해 이스케이프
data_json_safe = data_json.replace("</script", "<\\/script")

html = template.replace("/*__DASHBOARD_DATA__*/", data_json_safe)

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print("saved:", OUT, f"({len(html)/1024:.1f} KB)")
