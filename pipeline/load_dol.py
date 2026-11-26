"""Load DOL OFLC PERM + H-2A disclosure files, keep agriculture employers, cache as parquet.

Agriculture = NAICS 111 (crops), 112 (animal production), 1151/1152 (farm support).
"""
import glob, os, sys
import pandas as pd
from python_calamine import CalamineWorkbook

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "interim")
AG_PREFIXES = ("111", "112", "1151", "1152")

PERM_COLS = ["CASE_NUMBER", "CASE_STATUS", "DECISION_DATE", "OCCUPATION_TYPE", "EMP_BUSINESS_NAME",
    "EMP_TRADE_NAME", "EMP_ADDR1", "EMP_CITY", "EMP_STATE", "EMP_POSTCODE", "EMP_PHONE", "EMP_FEIN",
    "EMP_NAICS", "EMP_NUM_PAYROLL", "EMP_YEAR_COMMENCED", "EMP_POC_LAST_NAME", "EMP_POC_FIRST_NAME",
    "EMP_POC_JOB_TITLE", "EMP_POC_PHONE", "EMP_POC_EMAIL", "ATTY_AG_LAW_FIRM_NAME", "PWD_SOC_TITLE",
    "JOB_TITLE", "JOB_OPP_WAGE_FROM", "JOB_OPP_WAGE_PER", "PRIMARY_WORKSITE_CITY", "PRIMARY_WORKSITE_STATE"]
H2A_COLS = ["CASE_NUMBER", "CASE_STATUS", "DECISION_DATE", "TYPE_OF_EMPLOYER_APPLICATION", "H2A_LABOR_CONTRACTOR",
    "NATURE_OF_TEMPORARY_NEED", "EMPLOYER_NAME", "TRADE_NAME_DBA", "EMPLOYER_ADDRESS_1", "EMPLOYER_CITY",
    "EMPLOYER_STATE", "EMPLOYER_POSTAL_CODE", "EMPLOYER_PHONE", "EMPLOYER_FEIN", "NAICS_CODE",
    "EMPLOYER_POC_LAST_NAME", "EMPLOYER_POC_FIRST_NAME", "EMPLOYER_POC_JOB_TITLE", "EMPLOYER_POC_PHONE",
    "EMPLOYER_POC_EMAIL", "SOC_TITLE", "JOB_TITLE", "TOTAL_WORKERS_H2A_CERTIFIED", "EMPLOYMENT_BEGIN_DATE",
    "EMPLOYMENT_END_DATE", "WAGE_OFFER", "PER", "WORKSITE_CITY", "WORKSITE_STATE", "WORKSITE_COUNTY",
    "PHONE_TO_APPLY", "EMAIL_TO_APPLY", "WEBSITE_TO_APPLY"]


def read(path, cols):
    wb = CalamineWorkbook.from_path(path)
    rows = wb.get_sheet_by_name(wb.sheet_names[0]).to_python()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    return df[[c for c in cols if c in df.columns]].astype(str).replace({"None": "", "nan": ""})


def is_ag(naics):
    n = naics.str.replace(r"\.0$", "", regex=True).str.strip()
    return n.str.startswith(AG_PREFIXES)


def main():
    for kind, cols, ncol in (("PERM", PERM_COLS, "EMP_NAICS"), ("H-2A", H2A_COLS, "NAICS_CODE")):
        frames = []
        for f in sorted(glob.glob(os.path.join(RAW, f"{kind}_Disclosure_Data*.xlsx"))):
            df = read(f, cols)
            ag = df[is_ag(df[ncol])].copy()
            ag["SOURCE_FILE"] = os.path.basename(f)
            print(f"{os.path.basename(f)}: {len(df):,} rows, {len(ag):,} agriculture", file=sys.stderr)
            frames.append(ag)
        out = pd.concat(frames, ignore_index=True)
        out.to_parquet(os.path.join(OUT, f"{kind.lower().replace('-', '')}_ag.parquet"), index=False)


if __name__ == "__main__":
    main()
