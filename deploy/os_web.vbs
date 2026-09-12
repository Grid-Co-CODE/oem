Option Explicit
' sobe o OS Creator web sem janela e ESPERA o .cmd: a tarefa agendada fica Running enquanto o servico vive (IgnoreNew = sem duplicata)
Dim sh
Set sh = CreateObject("WScript.Shell")
WScript.Quit sh.Run("cmd.exe /c ""C:\GridcoBuild\oem\deploy\os_web.cmd""", 0, True)
