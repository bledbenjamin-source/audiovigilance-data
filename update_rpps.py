"""
Script de mise à jour automatique de la base RPPS — GitHub Action.
Colonnes réelles du fichier data.gouv.fr (vérifiées sur les logs) :
  SIRET  : "Numéro SIRET site"
  SIREN  : "Numéro SIREN site"
  Voie   : "Numéro Voie (coord. structure)" / "Libellé Voie (coord. structure)"
  Tél    : "Téléphone (coord. structure)" / "Téléphone 2 (coord. structure)"
"""
import io, re, sys
import requests
import pandas as pd

PARQUET_URL  = "https://object.files.data.gouv.fr/hydra-parquet/hydra-parquet/fffda7e9-0ea2-4c35-bba0-4496f3af935d.parquet"
OUTPUT       = "audio_pro_clean.parquet"
COL_CODE_PRO = "Code profession"

def _trouver_colonne(cols, *candidats):
    for c in candidats:
        if c in cols:
            return c
    return None

def _val(df, col):
    if col is None or col not in df.columns:
        return pd.Series("", index=df.index)
    return (df[col].fillna("")
                   .astype(str)
                   .str.strip()
                   .replace({"nan": "", "None": "", "NaN": ""}))

# ── Téléchargement ────────────────────────────────────────────────────────────
print("⬇️  Téléchargement du fichier RPPS...")
r = requests.get(PARQUET_URL, timeout=300, stream=True)
r.raise_for_status()
df_full = pd.read_parquet(io.BytesIO(r.content), engine="pyarrow")
print(f"✅ Fichier chargé : {len(df_full):,} lignes, {len(df_full.columns)} colonnes")

# ── Filtre audioprothésistes ──────────────────────────────────────────────────
df = df_full[df_full[COL_CODE_PRO].astype(str) == "26"].copy()
cols = set(df.columns)
print(f"✅ Audioprothésistes : {len(df):,} lignes")
print(f"📋 Toutes les colonnes : {sorted(cols)}")

# ── SIRET / SIREN — noms exacts du fichier ────────────────────────────────────
col_siret = _trouver_colonne(cols,
    "Numéro SIRET site",        # ← nom réel confirmé dans les logs
    "SIRET site",
    "Numéro SIRET",
    "SIRET",
)
col_siren = _trouver_colonne(cols,
    "Numéro SIREN site",        # ← nom réel confirmé dans les logs
    "Numéro SIREN",
    "SIREN",
)
print(f"➡️  SIRET : {col_siret or 'NON TROUVÉE'}")
print(f"➡️  SIREN : {col_siren or 'NON TROUVÉE'}")

siret_s = _val(df, col_siret).str.replace(r"\D", "", regex=True)
siren_s = _val(df, col_siren).str.replace(r"\D", "", regex=True)

df["siret_clean"] = siret_s.where(siret_s.str.len() == 14, "")
no_siret = df["siret_clean"] == ""
df.loc[no_siret, "siret_clean"] = siren_s.where(siren_s.str.len() == 9, "")[no_siret]

pct_siret = round(df["siret_clean"].ne("").sum() / len(df) * 100)
print(f"✅ siret_clean : {pct_siret}% ({df['siret_clean'].ne('').sum():,}/{len(df):,})")
if pct_siret == 0:
    print("❌ ERREUR : SIRET à 0%")
    sys.exit(1)

# ── Adresse — noms exacts du fichier (V majuscule) ────────────────────────────
col_num_voie = _trouver_colonne(cols,
    "Numéro Voie (coord. structure)",    # ← V majuscule, confirmé
    "Numéro voie (coord. structure)",
    "Numéro voie",
)
col_lib_voie = _trouver_colonne(cols,
    "Libellé Voie (coord. structure)",   # ← V majuscule, confirmé
    "Libellé voie (coord. structure)",
    "Libelle voie (coord. structure)",
    "Libellé voie",
)
print(f"➡️  Numéro Voie  : {col_num_voie or 'NON TROUVÉE'}")
print(f"➡️  Libellé Voie : {col_lib_voie or 'NON TROUVÉE'}")

num_v = _val(df, col_num_voie)
lib_v = _val(df, col_lib_voie)
df["adresse_clean"] = (num_v + " " + lib_v).str.strip()

pct_adr = round(df["adresse_clean"].ne("").sum() / len(df) * 100)
print(f"✅ adresse_clean : {pct_adr}%")

# ── Téléphone — noms exacts du fichier ───────────────────────────────────────
col_tel_s = _trouver_colonne(cols,
    "Téléphone (coord. structure)",      # ← confirmé
)
col_tel_pp = _trouver_colonne(cols,
    "Téléphone 2 (coord. structure)",    # ← confirmé (pas "coord. PP")
    "Téléphone (coord. PP)",
)
tel_s  = _val(df, col_tel_s)
tel_pp = _val(df, col_tel_pp)
df["tel_clean"] = tel_s.where(tel_s != "", tel_pp)

pct_tel = round(df["tel_clean"].ne("").sum() / len(df) * 100)
print(f"✅ tel_clean : {pct_tel}%")

# ── Enseigne commerciale ──────────────────────────────────────────────────────
col_enseigne = _trouver_colonne(cols,
    "Enseigne commerciale site",
    "Enseigne commerciale",
)
if col_enseigne:
    df["enseigne_clean"] = _val(df, col_enseigne)
    print(f"✅ enseigne_clean : {round(df['enseigne_clean'].ne('').sum()/len(df)*100)}%")

# ── Sauvegarde ────────────────────────────────────────────────────────────────
df.to_parquet(OUTPUT, engine="pyarrow", index=False)
print(f"\n✅ Parquet sauvegardé : {OUTPUT}")
print(f"   Lignes    : {len(df):,}")
print(f"   SIRET     : {pct_siret}%")
print(f"   Adresse   : {pct_adr}%")
print(f"   Téléphone : {pct_tel}%")
