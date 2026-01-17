class ComboCheck:
    def __init__(self):
        self._content = ""

    def read_file(self, file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            self._content = file.read()

    def contains(self, search_string):
        return self._content.find(search_string) != -1

    def append(self, string):
        self._content += string

invalid = ComboCheck()
checked = ComboCheck()
locked = ComboCheck()