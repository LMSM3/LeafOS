/* Windows DPAPI token vault. Compile: gcc token_vault.c -o token_vault.exe -lcrypt32 */
#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include <conio.h>
#include <dpapi.h>
#include <wincrypt.h>

#define VAULT_FILE "flower_token_vault.dat"
#define MAX_TXT 256

static void die(const char *msg) { fprintf(stderr, "[ERR] %s\n", msg); exit(1); }

static void sha256(const BYTE *in, DWORD inLen, BYTE out[32]) {
	HCRYPTPROV prov = 0; HCRYPTHASH hash = 0;
	CryptAcquireContext(&prov, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT);
	CryptCreateHash(prov, CALG_SHA_256, 0, 0, &hash);
	CryptHashData(hash, in, inLen, 0);
	DWORD len = 32; CryptGetHashParam(hash, HP_HASHVAL, out, &len, 0);
	CryptDestroyHash(hash); CryptReleaseContext(prov, 0);
}

static int read_pass(const char *prompt, char *buf, int max) {
	fprintf(stderr, "%s", prompt); fflush(stderr);
	int i = 0, c;
	while (i < max - 1 && (c = _getch()) != '\r' && c != '\n') {
		if (c == 3) { fprintf(stderr, "\n"); exit(1); }
		if (c == '\b' && i > 0) { i--; fprintf(stderr, "\b \b"); }
		else if (c != '\b') { buf[i++] = (char)c; fprintf(stderr, "*"); }
	}
	buf[i] = 0; fprintf(stderr, "\n");
	return i;
}

static char *vault_path(void) {
	static char path[MAX_PATH + 64];
	const char *home = getenv("USERPROFILE");
	if (!home) home = getenv("HOME");
	if (!home) die("USERPROFILE not set");
	snprintf(path, sizeof(path), "%s\\.cache\\huggingface\\%s", home, VAULT_FILE);
	return path;
}

static DATA_BLOB protect(const char *pwd, const DATA_BLOB *plain) {
	BYTE ent[32]; sha256((BYTE*)pwd, (DWORD)strlen(pwd), ent);
	DATA_BLOB entropy = { 32, ent }, out = {0};
	if (!CryptProtectData((DATA_BLOB*)plain, NULL, &entropy, NULL, NULL, 0, &out)) die("encrypt failed");
	return out;
}

static DATA_BLOB unprotect(const char *pwd, const DATA_BLOB *cipher) {
	BYTE ent[32]; sha256((BYTE*)pwd, (DWORD)strlen(pwd), ent);
	DATA_BLOB entropy = { 32, ent }, out = {0};
	if (!CryptUnprotectData((DATA_BLOB*)cipher, NULL, &entropy, NULL, NULL, 0, &out)) die("decrypt failed (wrong password?)");
	return out;
}

static void save_vault(void) {
	char r[MAX_TXT], w[MAX_TXT], pwd[MAX_TXT];
	read_pass("Password:     ", pwd, MAX_TXT);
	char p2[MAX_TXT]; read_pass("Confirm:      ", p2, MAX_TXT);
	if (strcmp(pwd, p2)) die("passwords do not match");
	fprintf(stderr, "Read token:   "); fflush(stderr); scanf("%255s", r);
	fprintf(stderr, "Write token:  "); fflush(stderr); scanf("%255s", w);
	char blob[512]; snprintf(blob, sizeof(blob), "read=%s\nwrite=%s\n", r, w);
	DATA_BLOB plain = { (DWORD)strlen(blob), (BYTE*)blob };
	DATA_BLOB cipher = protect(pwd, &plain);
	FILE *f = fopen(vault_path(), "wb");
	if (!f) die("cannot write vault");
	fwrite(cipher.pbData, 1, cipher.cbData, f); fclose(f);
	LocalFree(cipher.pbData);
	fprintf(stderr, "[+] Vault saved.\n");
}

static void get_token(const char *name) {
	char pwd[MAX_TXT];
	read_pass("Password: ", pwd, MAX_TXT);
	FILE *f = fopen(vault_path(), "rb");
	if (!f) die("vault not found; run save first");
	fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
	BYTE *buf = malloc(n); fread(buf, 1, n, f); fclose(f);
	DATA_BLOB cipher = { (DWORD)n, buf };
	DATA_BLOB plain = unprotect(pwd, &cipher);
	free(buf);
	char *text = (char*)plain.pbData; text[plain.cbData] = 0;
	char key[32]; snprintf(key, sizeof(key), "%s=", name);
	char *p = strstr(text, key);
	if (!p) die("token not found in vault");
	p += strlen(key);
	char *e = strchr(p, '\n'); if (e) *e = 0;
	printf("%s\n", p);
	LocalFree(plain.pbData);
}

int main(int argc, char **argv) {
	if (argc < 2) { printf("usage: token_vault.exe save | get read | get write\n"); return 1; }
	if (!strcmp(argv[1], "save")) save_vault();
	else if (!strcmp(argv[1], "get") && argc == 3) get_token(argv[2]);
	else die("bad command");
	return 0;
}
