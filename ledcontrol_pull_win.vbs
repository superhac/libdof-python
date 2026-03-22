Option Explicit

Dim mode, apikey, savefile, debugEnabled
mode = ""
apikey = ""
savefile = ""
debugEnabled = False

Dim arg
For Each arg In WScript.Arguments
    If LCase(Left(arg, 3)) = "/m=" Then
        mode = LCase(Mid(arg, 4))
    ElseIf LCase(Left(arg, 3)) = "/a=" Then
        apikey = Mid(arg, 4)
    ElseIf LCase(Left(arg, 3)) = "/f=" Then
        savefile = Mid(arg, 4)
    ElseIf LCase(arg) = "/d" Then
        debugEnabled = True
    End If
Next

If mode <> "version" And mode <> "download" Then
    WScript.Echo "ERROR: Missing or invalid /M=version|download"
    WScript.Quit 2
End If

If mode = "download" And savefile = "" Then
    WScript.Echo "ERROR: Missing /F=<zip path> for download mode"
    WScript.Quit 2
End If

Dim url
If mode = "version" Then
    url = "https://configtool.vpuniverse.com/api.php?query=version"
Else
    url = "https://configtool.vpuniverse.com/api.php?query=getconfig&apikey=" & apikey
End If

If debugEnabled Then WScript.Echo "DEBUG: mode=" & mode
If debugEnabled Then WScript.Echo "DEBUG: url=" & url

Dim http
Set http = CreateObject("MSXML2.XMLHTTP.6.0")
http.Open "GET", url, False
http.Send

If debugEnabled Then WScript.Echo "DEBUG: status=" & http.Status
If debugEnabled Then WScript.Echo "DEBUG: statusText=" & http.statusText
If debugEnabled Then
    On Error Resume Next
    WScript.Echo "DEBUG: header content-type=" & http.getResponseHeader("Content-Type")
    WScript.Echo "DEBUG: header content-length=" & http.getResponseHeader("Content-Length")
    WScript.Echo "DEBUG: header content-encoding=" & http.getResponseHeader("Content-Encoding")
    WScript.Echo "DEBUG: header server=" & http.getResponseHeader("Server")
    WScript.Echo "DEBUG: header cf-ray=" & http.getResponseHeader("CF-RAY")
    On Error GoTo 0
End If

If http.Status <> 200 Then
    WScript.Echo "ERROR: HTTP " & http.Status
    If Len(http.responseText) > 0 Then
        Dim preview
        preview = Replace(Replace(Left(http.responseText, 240), vbCr, "\r"), vbLf, "\n")
        WScript.Echo "ERROR: body=" & preview
    End If
    WScript.Quit 3
End If

If mode = "version" Then
    Dim txt
    txt = Trim(http.responseText)
    If debugEnabled Then WScript.Echo "DEBUG: version body len=" & Len(txt)
    If debugEnabled Then WScript.Echo "DEBUG: version body preview=" & Replace(Replace(Left(txt, 120), vbCr, "\r"), vbLf, "\n")
    If IsNumeric(txt) Then
        WScript.Echo txt
        WScript.Quit 0
    End If
    WScript.Echo "ERROR: Non-numeric version response"
    WScript.Echo "ERROR: body=" & Replace(Replace(Left(txt, 240), vbCr, "\r"), vbLf, "\n")
    WScript.Quit 4
End If

Dim stream
Set stream = CreateObject("ADODB.Stream")
stream.Type = 1
stream.Open
stream.Write http.responseBody
If debugEnabled Then WScript.Echo "DEBUG: download response bytes=" & LenB(http.responseBody)

' Validate ZIP signature before saving.
stream.Position = 0
Dim sig
sig = stream.Read(2)
If IsNull(sig) Then
    WScript.Echo "ERROR: Empty response body for download."
    stream.Close
    WScript.Quit 5
End If
If LenB(sig) < 2 Then
    WScript.Echo "ERROR: Response body too short for ZIP signature."
    stream.Close
    WScript.Quit 5
End If
If debugEnabled Then WScript.Echo "DEBUG: zip signature bytes=" & ByteHex(sig)
If AscB(MidB(sig, 1, 1)) <> &H50 Or AscB(MidB(sig, 2, 1)) <> &H4B Then
    Dim bodyPreview
    bodyPreview = Trim(http.responseText)
    bodyPreview = Replace(Replace(Left(bodyPreview, 240), vbCr, "\r"), vbLf, "\n")
    WScript.Echo "ERROR: Download response is not a ZIP payload."
    If Len(bodyPreview) > 0 Then
        WScript.Echo "ERROR: body=" & bodyPreview
    End If
    stream.Close
    WScript.Quit 6
End If

stream.Position = 0
If debugEnabled Then WScript.Echo "DEBUG: savefile=" & savefile
stream.SaveToFile savefile, 2
stream.Close

If debugEnabled Then
    Dim fso
    Set fso = CreateObject("Scripting.FileSystemObject")
    If fso.FileExists(savefile) Then
        WScript.Echo "DEBUG: saved file size=" & fso.GetFile(savefile).Size
    Else
        WScript.Echo "DEBUG: saved file not found after SaveToFile"
    End If
End If

WScript.Echo "OK"
WScript.Quit 0

Function ByteHex(bytes)
    If IsNull(bytes) Then
        ByteHex = "<null>"
        Exit Function
    End If
    Dim n, i, out, hx
    n = LenB(bytes)
    out = ""
    For i = 1 To n
        hx = Hex(AscB(MidB(bytes, i, 1)))
        If Len(hx) = 1 Then hx = "0" & hx
        If i > 1 Then out = out & " "
        out = out & hx
    Next
    ByteHex = out
End Function
