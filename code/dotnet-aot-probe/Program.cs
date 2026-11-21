using System.Runtime.InteropServices;

var sw = System.Diagnostics.Stopwatch.StartNew();
Console.WriteLine($"arch = {RuntimeInformation.ProcessArchitecture}");
Console.WriteLine($"os   = {RuntimeInformation.OSDescription}");
Console.WriteLine($"path = {Environment.ProcessPath}");
Console.WriteLine($"startup_ms(含启动) ≈ {sw.Elapsed.TotalMilliseconds:F1}");
