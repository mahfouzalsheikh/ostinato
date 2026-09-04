/* Read and operate the official converter's Win32 controls under 32-bit Wine.
 * Tree items live in the converter process; marshal TVITEM explicitly rather
 * than passing a pointer to this helper's address space. No style decoding.
 */
#include <windows.h>
#include <commctrl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static BOOL CALLBACK list_child(HWND window, LPARAM unused) {
    char class_name[128] = {0}, text[1024] = {0};
    GetClassNameA(window, class_name, sizeof(class_name));
    SendMessageA(window, WM_GETTEXT, sizeof(text), (LPARAM)text);
    printf("%lx id=%d %s %s\n", (unsigned long)window,
           GetDlgCtrlID(window), class_name, text);
    return TRUE;
}

static BOOL CALLBACK list_window(HWND window, LPARAM unused) {
    if (IsWindowVisible(window)) {
        list_child(window, 0);
        EnumChildWindows(window, list_child, 0);
    }
    return TRUE;
}

static void tree_text(HWND window, HTREEITEM item, char text[512]) {
    DWORD process_id;
    GetWindowThreadProcessId(window, &process_id);
    HANDLE process = OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ |
                                 PROCESS_VM_WRITE, FALSE, process_id);
    if (!process) {
        fprintf(stderr, "cannot read converter process\n");
        exit(2);
    }
    void *memory = VirtualAllocEx(process, NULL, 1024,
                                 MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!memory) {
        CloseHandle(process);
        fprintf(stderr, "cannot marshal tree item\n");
        exit(2);
    }
    TVITEMA value = {0};
    value.mask = TVIF_TEXT;
    value.hItem = item;
    value.pszText = (char *)memory + sizeof(value);
    value.cchTextMax = 500;
    BOOL written = WriteProcessMemory(process, memory, &value, sizeof(value), NULL);
    LRESULT read_item = written && SendMessageA(window, TVM_GETITEMA, 0, (LPARAM)memory);
    BOOL copied = read_item && ReadProcessMemory(process, value.pszText, text, 500, NULL);
    text[500] = '\0';
    VirtualFreeEx(process, memory, 0, MEM_RELEASE);
    CloseHandle(process);
    if (!copied) {
        fprintf(stderr, "cannot read tree item\n");
        exit(2);
    }
}

static void list_tree(HWND window, HTREEITEM item, int depth) {
    while (item) {
        char text[512] = {0};
        tree_text(window, item, text);
        printf("%lx %d %s\n", (unsigned long)item, depth, text);
        HTREEITEM child = (HTREEITEM)SendMessageA(window, TVM_GETNEXTITEM,
                                               TVGN_CHILD, (LPARAM)item);
        list_tree(window, child, depth + 1);
        item = (HTREEITEM)SendMessageA(window, TVM_GETNEXTITEM,
                                     TVGN_NEXT, (LPARAM)item);
    }
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "list") == 0) {
        EnumWindows(list_window, 0);
        return 0;
    }
    if (argc < 3) return 1;
    HWND window = (HWND)strtoul(argv[2], NULL, 16);
    if (!IsWindow(window)) return 2;
    if (strcmp(argv[1], "tree") == 0) {
        list_tree(window, (HTREEITEM)SendMessageA(window, TVM_GETNEXTITEM,
                                                TVGN_ROOT, 0), 0);
    } else if (strcmp(argv[1], "text") == 0 && argc == 4) {
        SendMessageA(window, WM_SETTEXT, 0, (LPARAM)argv[3]);
    } else if (strcmp(argv[1], "click") == 0) {
        SendMessageA(window, BM_CLICK, 0, 0);
    } else if (strcmp(argv[1], "select") == 0 && argc >= 4) {
        SendMessageA(window, TVM_SELECTITEM, TVGN_CARET,
                     (LPARAM)strtoul(argv[3], NULL, 16));
        SetFocus(window);
        if (argc > 4) {
            SendMessageA(window, WM_KEYDOWN, VK_RETURN, 0);
            SendMessageA(window, WM_KEYUP, VK_RETURN, 0);
        }
    } else {
        return 1;
    }
    return 0;
}
