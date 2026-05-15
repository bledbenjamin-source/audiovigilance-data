"""
Script de mise à jour automatique de la base RPPS.
Télécharge le fichier data.gouv.fr, filtre les audioprothésistes (code 26),
normalise les colonnes, et sauvegarde en Parquet.
"""
import io, re
import requests
import pandas as pd

PARQUET_URL = "https://object.files.data.gouv.fr/hydra-parquet/hydra-parquet/fffda7e9-0ea2-4c35-bba0-4496f3af935d.parquet"
OUTPUT      = "audio_pro_clean.parquet"
COL_CODE_PRO = "Code profession"

def _trouver_colonne(cols, *candidats):
    for c in candidats:
        if c in cols: return c
    return None

def _val(df, col):
    if col is None or col not in df.columns:
        return pd.Series("", index=df.index)
    return (df[col].fillna("").astype(str).str.strip()
            .replace({"nan":"","None":"","NaN":""}))

print("⬇️  Téléchargement du fichier RPPS...")
r = requests.get(PARQUET_URL, timeout=180, stream=True)
r.raise_for_status()
df_full = pd.read_parquet(io.BytesIO(r.content), engine="pyarrow")
print(f"✅ Fichier chargé : {len(df_full):,} lignes")

# Filtrer uniquement audioprothésistes (code 26)
df = df_full[df_full[COL_CODE_PRO].astype(str) == "26"].copy()
cols = set(df.columns)
print(f"✅ Audioprothésistes filtrés : {len(df):,} lignes")

# SIRET
col_siret = _trouver_colonne(cols, "SIRET site","Numéro SIRET","SIRET","siret")
col_siren  = _trouver_colonne(cols, "Numéro SIREN","SIREN")
siret_s = _val(df, col_siret).str.replace(r"\D","",regex=True)
siren_s = _val(df, col_siren).str.replace(r"\D","",regex=True)
df["siret_clean"] = siret_s.where(siret_s.str.len()==14,"")
no_siret = df["siret_clean"]==""
df.loc[no_siret,"siret_clean"] = siren_s.where(siren_s.str.len()==9,"")[no_siret]

# Adresse
col_num  = _trouver_colonne(cols, "Numéro voie (coord. structure)","Numéro voie")
col_voie = _trouver_colonne(cols, "Libellé voie (coord. structure)","Libellé voie","Libelle voie")
col_adr  = _trouver_colonne(cols, "Adresse postale (coord. structure)","Adresse postale")
df["adresse_clean"] = (_val(df,col_num)+" "+_val(df,col_voie)).str.strip()
vide = df["adresse_clean"].str.strip()==""
df.loc[vide,"adresse_clean"] = _val(df,col_adr)[vide]

# Téléphone
col_tel_s  = _trouver_colonne(cols, "Téléphone (coord. structure)","Telephone (coord. structure)")
col_tel_pp = _trouver_colonne(cols, "Téléphone (coord. PP)","Telephone (coord. PP)")
tel_s = _val(df, col_tel_s); tel_pp = _val(df, col_tel_pp)
df["tel_clean"] = tel_s.where(tel_s!="", tel_pp)

# Stats
n = len(df)
pct_siret = round(df["siret_clean"].ne("").sum()/n*100)
pct_adr   = round(df["adresse_clean"].ne("").sum()/n*100)
pct_tel   = round(df["tel_clean"].ne("").sum()/n*100)
print(f"📊 SIRET:{pct_siret}% | Adresse:{pct_adr}% | Téléphone:{pct_tel}%")

df.to_parquet(OUTPUT, engine="pyarrow", index=False)
print(f"✅ Fichier sauvegardé : {OUTPUT}")
