# Cached pastel backdrop and frosted glass surfaces; native input behavior is preserved.
function Write-UiPreview($Window, [string]$Path) {
    if (-not $Path) { return }
    $Window.CreateControl()
    foreach ($control in $Window.Controls) { $control.CreateControl() }
    $bitmap = New-Object Drawing.Bitmap($Window.Width, $Window.Height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    function Draw-PreviewChildren($Parent, $Graphics, [int]$X, [int]$Y) {
        # Hidden forms omit descendants in DrawToBitmap. Composite each child
        # directly, without showing a window or taking over the user's screen.
        for ($index = $Parent.Controls.Count - 1; $index -ge 0; $index--) {
            $child = $Parent.Controls[$index]
            if (-not [WorkdaySoftTheme]::OwnVisible($child) -or $child.Width -le 0 -or $child.Height -le 0) { continue }
            $left = $X + $child.Left; $top = $Y + $child.Top
            $rect = New-Object Drawing.RectangleF($left, $top, $child.Width, $child.Height)
            $backColor = $child.BackColor
            if($child -is [Windows.Forms.Button]){$backColor=$Parent.BackColor}
            if ($child -is [Windows.Forms.DataGridView]) { $backColor = $child.BackgroundColor }
            $background = New-Object Drawing.SolidBrush($backColor)
            $ink = New-Object Drawing.SolidBrush($child.ForeColor)
            try {
                if($child -is [Windows.Forms.Panel] -or $child -is [Windows.Forms.GroupBox]){[WorkdaySoftTheme]::Glass($Graphics,$Window,$rect,20,$false,155)}elseif($child -isnot [Windows.Forms.Button]){$Graphics.FillRectangle($background,$rect)}
                if ($child -is [Windows.Forms.DataGridView]) {
                    $headerBrush = New-Object Drawing.SolidBrush($child.ColumnHeadersDefaultCellStyle.BackColor)
                    $whiteBrush = New-Object Drawing.SolidBrush($child.ColumnHeadersDefaultCellStyle.ForeColor)
                    $cellInk = New-Object Drawing.SolidBrush($child.DefaultCellStyle.ForeColor)
                    $columns=@($child.Columns|Where-Object{$_.Visible});$weights = ($columns | Measure-Object -Property FillWeight -Sum).Sum
                    $cx = [single]$left
                    try {
                        foreach ($column in $columns) {
                            $cw = [single]$column.Width
                            $Graphics.FillRectangle($headerBrush, $cx, $top, $cw, 40)
                            $format=New-Object Drawing.StringFormat;$format.Alignment='Center';$format.LineAlignment='Center';$format.FormatFlags=[Drawing.StringFormatFlags]::NoWrap;$format.Trimming='EllipsisCharacter';$Graphics.DrawString($column.HeaderText,$child.Font,$whiteBrush,(New-Object Drawing.RectangleF($cx,$top,$cw,40)),$format);$format.Dispose()
                            $cy = $top + 40
                            foreach ($row in $child.Rows) {
                                $value = $row.Cells[$column.Index].Value
                                $text = [string]$value
                                if ($column -is [Windows.Forms.DataGridViewCheckBoxColumn]) { if ($value) { $text = '☑' } else { $text = '☐' } }
                                $format=New-Object Drawing.StringFormat;$format.Alignment='Center';$format.LineAlignment='Center';$format.FormatFlags=[Drawing.StringFormatFlags]::NoWrap;$format.Trimming='EllipsisCharacter';$Graphics.DrawString($text,$child.Font,$cellInk,(New-Object Drawing.RectangleF($cx,$cy,$cw,32)),$format);$format.Dispose()
                                $cy += 32
                            }
                            $cx += $cw
                        }
                    } finally { $headerBrush.Dispose(); $whiteBrush.Dispose(); $cellInk.Dispose() }
                } elseif($child -is [Windows.Forms.Button]) {
                    [WorkdaySoftTheme]::PreviewButton($Graphics,$rect,$child)
                } elseif ($child -isnot [Windows.Forms.Panel] -and $child -isnot [Windows.Forms.GroupBox]) {
                    $text = $child.Text
                    if ($child -is [Windows.Forms.DateTimePicker]) { $text = $child.Value.ToString($child.CustomFormat) }
                    if($child -is [Windows.Forms.ComboBox]){$text=[string]$child.SelectedItem}
                    if($child -is [Windows.Forms.NumericUpDown]){$text=[string]$child.Value}
                    if ($child -is [Windows.Forms.CheckBox]) { $text = $(if ($child.Checked) { '☑ ' } else { '☐ ' }) + $text }
                    $format = New-Object Drawing.StringFormat
                    try {
                        $format.LineAlignment = [Drawing.StringAlignment]::Center
                        if($child -is [Windows.Forms.Label]){if($child.TextAlign.ToString() -match 'Center$'){$format.Alignment='Center'}elseif($child.TextAlign.ToString() -match 'Right$'){$format.Alignment='Far'};if($child.Text -notmatch "`n"){$format.FormatFlags=[Drawing.StringFormatFlags]::NoWrap}}
                        if ($child -is [Windows.Forms.Button] -or $child -is [Windows.Forms.ComboBox] -or $child -is [Windows.Forms.NumericUpDown] -or $child -is [Windows.Forms.DateTimePicker] -or $child -is [Windows.Forms.TextBox]) { $format.Alignment = [Drawing.StringAlignment]::Center }
                        $textRect = New-Object Drawing.RectangleF(($left + $child.Padding.Left + 4), $top, ($child.Width - $child.Padding.Left), $child.Height)
                        if($child -is [Windows.Forms.ComboBox] -or $child -is [Windows.Forms.NumericUpDown] -or $child -is [Windows.Forms.DateTimePicker]){$textRect.Width-=23};$Graphics.DrawString($text, $child.Font, $ink, $textRect, $format)
                        if($child -is [Windows.Forms.ComboBox] -or $child -is [Windows.Forms.NumericUpDown] -or $child -is [Windows.Forms.DateTimePicker]){[WorkdaySoftTheme]::PreviewArrow($Graphics,(New-Object Drawing.Rectangle(($left+$child.Width-24),($top+2),22,($child.Height-4))),($child -isnot [Windows.Forms.ComboBox]),$child.Enabled)}
                    } finally { $format.Dispose() }
                }
                if ($child -is [Windows.Forms.Panel] -or $child -is [Windows.Forms.GroupBox]) { Draw-PreviewChildren $child $Graphics $left $top }
            } finally { $background.Dispose(); $ink.Dispose() }
        }
    }
    try {
        $Window.DrawToBitmap($bitmap, (New-Object Drawing.Rectangle(0, 0, $Window.Width, $Window.Height)))
        $border = [int](($Window.Width - $Window.ClientSize.Width) / 2)
        Draw-PreviewChildren $Window $graphics $border ($Window.Height - $Window.ClientSize.Height - $border)
        $bitmap.Save($Path, [Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
if (-not ('WorkdaySoftTheme' -as [type])) {
 Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public static class WorkdaySoftTheme {
 public static readonly Color Surface=Color.FromArgb(241,244,245), Ink=Color.FromArgb(52,71,91);
 static Color Mix(Color a,Color b,float t){return Color.FromArgb((int)(a.R+(b.R-a.R)*t),(int)(a.G+(b.G-a.G)*t),(int)(a.B+(b.B-a.B)*t));}
 static GraphicsPath Round(RectangleF r,float radius){GraphicsPath p=new GraphicsPath();float d=Math.Min(radius*2,Math.Min(r.Width,r.Height));if(d<=0){p.AddRectangle(r);return p;}p.AddArc(r.X,r.Y,d,d,180,90);p.AddArc(r.Right-d,r.Y,d,d,270,90);p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);p.AddArc(r.X,r.Bottom-d,d,d,90,90);p.CloseFigure();return p;}
 static readonly MethodInfo State=typeof(Control).GetMethod("GetState",BindingFlags.NonPublic|BindingFlags.Instance);
 public static bool OwnVisible(Control c){return State==null?true:(bool)State.Invoke(c,new object[]{2});}
 class Scene:IDisposable{
  public Bitmap Image,Frosted;public Size Size;
  public void Dispose(){if(Image!=null){Image.Dispose();Image=null;}if(Frosted!=null){Frosted.Dispose();Frosted=null;}}
 }
 static ConditionalWeakTable<Form,Scene> Scenes=new ConditionalWeakTable<Form,Scene>();
 static void Glow(Graphics g,RectangleF area,Color color){using(var p=new GraphicsPath()){p.AddEllipse(area);using(var brush=new PathGradientBrush(p)){brush.CenterColor=color;brush.SurroundColors=new Color[]{Color.FromArgb(0,color)};g.FillPath(brush,p);}}}
 static Bitmap SceneImage(Form form){
  var scene=Scenes.GetValue(form,f=>{var item=new Scene();f.Disposed+=(a,b)=>item.Dispose();return item;});
  Size size=form.ClientSize;if(size.Width<1||size.Height<1)return null;
  if(scene.Image!=null&&scene.Size==size)return scene.Image;
  scene.Dispose();scene.Size=size;scene.Image=new Bitmap(size.Width,size.Height,System.Drawing.Imaging.PixelFormat.Format32bppPArgb);
  using(var g=Graphics.FromImage(scene.Image)){
   g.SmoothingMode=SmoothingMode.AntiAlias;using(var brush=new LinearGradientBrush(new Rectangle(Point.Empty,size),Color.FromArgb(190,209,227),Color.FromArgb(218,229,240),90f))g.FillRectangle(brush,new Rectangle(Point.Empty,size));
   float w=size.Width,h=size.Height;
   Glow(g,new RectangleF(-w*.45f,-h*.28f,w*1.45f,h*.9f),Color.FromArgb(235,242,177,121));
   Glow(g,new RectangleF(w*.28f,-h*.18f,w*1.3f,h*.92f),Color.FromArgb(140,144,164,196));
   Glow(g,new RectangleF(-w*.4f,h*.32f,w*1.25f,h*.92f),Color.FromArgb(210,240,180,127));
   Glow(g,new RectangleF(w*.32f,h*.55f,w*1.1f,h*.75f),Color.FromArgb(100,177,202,217));
   using(var wash=new SolidBrush(Color.FromArgb(40,255,255,255)))g.FillRectangle(wash,new Rectangle(Point.Empty,size));
  }
  // Cache a further diffused version for card surfaces. Native text remains
  // outside this bitmap, so only the backdrop is softened.
  scene.Frosted=new Bitmap(size.Width,size.Height,System.Drawing.Imaging.PixelFormat.Format32bppPArgb);
  using(var small=new Bitmap(Math.Max(1,size.Width/18),Math.Max(1,size.Height/18))){
   using(var g=Graphics.FromImage(small)){g.InterpolationMode=InterpolationMode.HighQualityBilinear;g.DrawImage(scene.Image,new Rectangle(Point.Empty,small.Size));}
   using(var g=Graphics.FromImage(scene.Frosted)){g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(small,new Rectangle(Point.Empty,size));}
  }return scene.Image;
 }
 static Point SceneOrigin(Control control){Point origin=Point.Empty;for(Control c=control;c!=null&&!(c is Form);c=c.Parent){origin.Offset(c.Left,c.Top);}return origin;}
 public static void DrawScene(Graphics g,Control control){DrawBackdrop(g,control,false);}
 static void DrawBackdrop(Graphics g,Control control,bool frosted){var form=control as Form??control.FindForm();if(form==null)return;var image=SceneImage(form);if(image==null)return;Scene scene;if(frosted&&Scenes.TryGetValue(form,out scene)&&scene.Frosted!=null)image=scene.Frosted;Point origin=SceneOrigin(control);g.DrawImageUnscaled(image,-origin.X,-origin.Y);}
 static void Shadow(Graphics g,RectangleF r,float radius){for(int i=5;i>=1;i--){var shadow=r;shadow.Offset(0,i*.8f);shadow.Inflate(i*.3f,i*.2f);using(var p=Round(shadow,radius))using(var fill=new SolidBrush(Color.FromArgb(4,65,78,116)))g.FillPath(fill,p);}}
 public static void Glass(Graphics g,Control context,RectangleF r,float radius,bool shadow,int white){
  if(r.Width<2||r.Height<2)return;var state=g.Save();g.SmoothingMode=SmoothingMode.AntiAlias;if(shadow)Shadow(g,r,radius);
  using(var p=Round(r,radius)){
   g.SetClip(p,CombineMode.Intersect);DrawBackdrop(g,context,true);
   using(var wash=new LinearGradientBrush(r,Color.FromArgb(Math.Min(255,white+30),255,255,255),Color.FromArgb(white,247,250,255),100f))g.FillPath(wash,p);
   using(var sheen=new LinearGradientBrush(new RectangleF(r.X,r.Y,r.Width,Math.Max(2,r.Height*.34f)),Color.FromArgb(36,255,255,255),Color.FromArgb(0,255,255,255),90f))g.FillRectangle(sheen,r.X,r.Y,r.Width,r.Height*.34f);
   g.Restore(state);g.SmoothingMode=SmoothingMode.AntiAlias;
   using(var rim=new Pen(Color.FromArgb(210,255,255,255),1))g.DrawPath(rim,p);
  }
 }
 public static void SurfacePaint(Graphics g,RectangleF r,float radius,Color color,bool raised){
  if(r.Width<2||r.Height<2)return;g.SmoothingMode=SmoothingMode.AntiAlias;if(raised)Shadow(g,r,radius);
  bool dark=color.GetBrightness()<.64f;
  using(var p=Round(r,radius))using(var brush=new LinearGradientBrush(r,Mix(color,Color.White,dark?.07f:.35f),dark?Mix(color,Ink,.22f):Mix(color,Surface,.1f),95f)){
   g.FillPath(brush,p);var state=g.Save();g.SetClip(p,CombineMode.Intersect);
   using(var light=new LinearGradientBrush(new RectangleF(r.X,r.Y,r.Width,Math.Max(2,r.Height*.42f)),Color.FromArgb(dark?24:70,255,255,255),Color.FromArgb(0,255,255,255),90f))g.FillRectangle(light,r.X,r.Y,r.Width,r.Height*.42f);
   g.Restore(state);using(var edge=new Pen(Color.FromArgb(dark?145:220,255,255,255),1))g.DrawPath(edge,p);
  }
 }
 public static void Inset(Graphics g,RectangleF r,float radius,Color color){
  SurfacePaint(g,r,radius,Mix(color,Ink,color.GetBrightness()<.64f?.08f:.045f),false);
  using(var p=Round(RectangleF.Inflate(r,-1,-1),Math.Max(2,radius-1)))using(var pen=new Pen(Color.FromArgb(45,67,94,122),1.5f))g.DrawPath(pen,p);
 }
 class ButtonState{public ButtonState(){} public bool Down,Hover,Selected;}
 static ConditionalWeakTable<Button,ButtonState> Buttons=new ConditionalWeakTable<Button,ButtonState>();
 public static bool IsPressed(Button b){ButtonState state;return Buttons.TryGetValue(b,out state)&&(state.Down||state.Selected);}
 public static void SetSelected(Button b,bool selected){var state=Buttons.GetOrCreateValue(b);state.Selected=selected;b.Invalidate();if(b.Parent!=null)b.Parent.Invalidate(Rectangle.Inflate(b.Bounds,8,8));}
 public static void ButtonPaint(Graphics g,Rectangle r,Button b,bool pressed,bool hover){
  RectangleF face=new RectangleF(r.X+1,r.Y+1,r.Width-3,r.Height-3);Color fill=b.Enabled?b.BackColor:Surface;
  if(pressed)fill=Mix(fill,Ink,.10f);else if(hover)fill=Mix(fill,Color.White,.10f);
  if(pressed||IsPressed(b))Inset(g,face,Math.Max(2,(r.Height-3)/2f),fill);else if(fill.GetBrightness()>.64f)Glass(g,b,face,Math.Max(2,(r.Height-3)/2f),false,180);else SurfacePaint(g,face,Math.Max(2,(r.Height-3)/2f),fill,false);
  Color text=!b.Enabled?Color.FromArgb(126,139,148):(fill.GetBrightness()>.64f?Ink:Color.White);
  Rectangle content=Rectangle.Inflate(r,-5,-2);if(pressed)content.Offset(1,1);
  TextRenderer.DrawText(g,b.Text,b.Font,content,text,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.SingleLine|TextFormatFlags.EndEllipsis);
  if(b.Focused)using(var p=Round(RectangleF.Inflate(face,-3,-3),10))using(var pen=new Pen(Color.FromArgb(100,80,112,136),1)){pen.DashStyle=DashStyle.Dot;g.DrawPath(pen,p);}
 }
 public static void PreviewButton(Graphics g,RectangleF r,Button b){
  Color fill=b.Enabled?b.BackColor:Surface;
  var face=new RectangleF(r.X+1,r.Y+1,r.Width-3,r.Height-3);if(IsPressed(b))Inset(g,face,Math.Max(2,(r.Height-3)/2f),fill);else if(fill.GetBrightness()>.64f)Glass(g,b.FindForm(),face,Math.Max(2,(r.Height-3)/2f),false,180);else SurfacePaint(g,face,Math.Max(2,(r.Height-3)/2f),fill,false);
  Color text=!b.Enabled?Color.FromArgb(126,139,148):(fill.GetBrightness()>.64f?Ink:Color.White);
  using(var brush=new SolidBrush(text))using(var format=new StringFormat()){format.Alignment=StringAlignment.Center;format.LineAlignment=StringAlignment.Center;g.DrawString(b.Text,b.Font,brush,RectangleF.Inflate(r,-5,-2),format);}
 }
 public static void ApplyButton(Button b){
  var state=Buttons.GetOrCreateValue(b);b.FlatStyle=FlatStyle.Flat;b.FlatAppearance.BorderSize=0;
  b.Paint+=(s,e)=>ButtonPaint(e.Graphics,b.ClientRectangle,b,state.Down,state.Hover);
  b.MouseEnter+=(s,e)=>{state.Hover=true;b.Invalidate();};b.MouseLeave+=(s,e)=>{state.Hover=false;state.Down=false;b.Invalidate();if(b.Parent!=null)b.Parent.Invalidate(Rectangle.Inflate(b.Bounds,8,8));};b.MouseDown+=(s,e)=>{state.Down=true;b.Invalidate();if(b.Parent!=null)b.Parent.Invalidate(Rectangle.Inflate(b.Bounds,8,8));};b.MouseUp+=(s,e)=>{state.Down=false;b.Invalidate();if(b.Parent!=null)b.Parent.Invalidate(Rectangle.Inflate(b.Bounds,8,8));};
  b.EnabledChanged+=(s,e)=>b.Invalidate();b.GotFocus+=(s,e)=>b.Invalidate();b.LostFocus+=(s,e)=>b.Invalidate();
  EventHandler size=(s,e)=>{var old=b.Region;using(var p=Round(new RectangleF(0,0,b.Width,b.Height),Math.Max(2,(b.Height-1)/2f)))b.Region=new Region(p);if(old!=null)old.Dispose();};size(b,EventArgs.Empty);b.SizeChanged+=size;
 }
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern IntPtr FindWindowEx(IntPtr parent,IntPtr after,string name,string text);
 [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr hwnd,out NativeRect r);
 [StructLayout(LayoutKind.Sequential)] struct NativeRect{public int Left,Top,Right,Bottom;}
 static ConditionalWeakTable<Control,InputDecoration> Inputs=new ConditionalWeakTable<Control,InputDecoration>();
 class ArrowWindow:NativeWindow{
  Control owner;bool combo;int pressed=-1;
  public ArrowWindow(Control value,IntPtr handle,bool drop){owner=value;combo=drop;AssignHandle(handle);}
  protected override void WndProc(ref Message m){
   if(m.Msg==0x201)pressed=((int)((long)m.LParam>>16))&65535;
   if(m.Msg==0x202||m.Msg==0x215)pressed=-1;
   base.WndProc(ref m);
   if((m.Msg==0xF||m.Msg==0x85||m.Msg==0x317||m.Msg==0x318)&&Handle!=IntPtr.Zero){
    try{using(var g=(m.Msg==0x317||m.Msg==0x318)&&m.WParam!=IntPtr.Zero?Graphics.FromHdc(m.WParam):Graphics.FromHwnd(Handle)){
     NativeRect bounds;if(!GetClientRect(Handle,out bounds))return;
     int width=bounds.Right,height=bounds.Bottom;
     if(combo){int aw=Math.Min(28,width);PaintArrow(g,new Rectangle(width-aw+1,2,aw-3,height-4),false,false,owner.Enabled);}
     else{int half=height/2;PaintArrow(g,new Rectangle(1,1,width-2,half-2),true,pressed>=0&&pressed<half,owner.Enabled);PaintArrow(g,new Rectangle(1,half+1,width-2,height-half-2),false,pressed>=half,owner.Enabled);}
    }}catch(ObjectDisposedException){}catch(ArgumentException){}catch(ExternalException){}
   }
  }
 }
 public static void PreviewArrow(Graphics g,Rectangle r,bool spin,bool enabled){if(!spin){PaintArrow(g,r,false,false,enabled);return;}int half=r.Height/2;PaintArrow(g,new Rectangle(r.X,r.Y,r.Width,half-1),true,false,enabled);PaintArrow(g,new Rectangle(r.X,r.Y+half+1,r.Width,r.Height-half-1),false,false,enabled);}
 public static int InputSkinCount(Control input){InputDecoration value;return Inputs.TryGetValue(input,out value)?value.Count:0;}
 static void PaintArrow(Graphics g,Rectangle rect,bool up,bool pressed,bool enabled){
  if(rect.Width<3||rect.Height<3)return;
  Color fill=enabled?Color.FromArgb(82,103,125):Color.FromArgb(203,213,221);
  if(pressed)Inset(g,rect,5,fill);else SurfacePaint(g,rect,5,fill,false);
  float x=rect.Left+rect.Width/2f,y=rect.Top+rect.Height/2f;float k=Math.Min(4,rect.Width/4f);
  using(var pen=new Pen(enabled?Color.White:Ink,1.4f)){g.SmoothingMode=SmoothingMode.AntiAlias;g.DrawLines(pen,new PointF[]{new PointF(x-k,y+(up?1:-1)),new PointF(x,y+(up?-2:2)),new PointF(x+k,y+(up?1:-1))});}
 }
 class InputDecoration{
  public int Count{get{return arrows.Count;}}
  Control owner;List<ArrowWindow> arrows=new List<ArrowWindow>();HashSet<IntPtr> handles=new HashSet<IntPtr>();
  void Add(IntPtr handle,bool combo){if(handle!=IntPtr.Zero&&handles.Add(handle))arrows.Add(new ArrowWindow(owner,handle,combo));}
  public InputDecoration(Control value){owner=value;owner.HandleCreated+=(s,e)=>Bind();owner.VisibleChanged+=(s,e)=>Bind();owner.HandleDestroyed+=(s,e)=>Clear();owner.Disposed+=(s,e)=>Clear();foreach(Control child in owner.Controls){child.HandleCreated+=(s,e)=>Bind();}owner.ControlAdded+=(s,e)=>{e.Control.HandleCreated+=(a,b)=>Bind();};owner.EnabledChanged+=(s,e)=>owner.Invalidate();Bind();}
  void Clear(){foreach(var arrow in arrows)if(arrow.Handle!=IntPtr.Zero)arrow.ReleaseHandle();arrows.Clear();handles.Clear();}
  void Bind(){if(owner.IsDisposed||!owner.IsHandleCreated)return;
   if(owner is ComboBox)Add(owner.Handle,true);
   else if(owner is DateTimePicker)Add(FindWindowEx(owner.Handle,IntPtr.Zero,"msctls_updown32",null),false);
   else if(owner is NumericUpDown)foreach(Control child in owner.Controls)if(!(child is TextBox)&&child.IsHandleCreated)Add(child.Handle,false);
  }
 }
 public static void Input(Control input){
  InputDecoration prior;if(Inputs.TryGetValue(input,out prior))return;Inputs.GetValue(input,c=>new InputDecoration(c));
  var combo=input as ComboBox;
  if(combo!=null){combo.DrawMode=DrawMode.OwnerDrawFixed;combo.ItemHeight=23;combo.DropDownHeight=220;
   combo.DrawItem+=(s,e)=>{if(e.Index<0)return;bool selected=(e.State&DrawItemState.Selected)!=0;using(var bg=new SolidBrush(selected?Color.FromArgb(221,231,239):Color.FromArgb(247,249,250)))e.Graphics.FillRectangle(bg,e.Bounds);
    var flags=TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.SingleLine|TextFormatFlags.EndEllipsis;
    Rectangle text=e.Bounds;if((e.State&DrawItemState.ComboBoxEdit)!=0)text.Width=Math.Max(0,text.Width-7);
    TextRenderer.DrawText(e.Graphics,combo.GetItemText(combo.Items[e.Index]),combo.Font,text,Ink,flags);
   };
  }
 }
 public static void Group(GroupBox group){
  string caption=group.Text;group.Text="";
  var label=new Label{Text=caption,TextAlign=ContentAlignment.MiddleCenter,AutoSize=false,BackColor=Color.Transparent,ForeColor=Ink,Location=new Point(10,5),Size=new Size(group.Width-20,24),Anchor=AnchorStyles.Top|AnchorStyles.Left|AnchorStyles.Right};group.Controls.Add(label);

 }
 public static void Container(Control parent){
  if(parent is Panel){EventHandler size=(s,e)=>{var old=parent.Region;using(var p=Round(new RectangleF(0,0,parent.Width,parent.Height),20))parent.Region=new Region(p);if(old!=null)old.Dispose();};size(parent,EventArgs.Empty);parent.SizeChanged+=size;}
  var buffered=typeof(Control).GetProperty("DoubleBuffered",BindingFlags.NonPublic|BindingFlags.Instance);if(buffered!=null)buffered.SetValue(parent,true,null);
  parent.Paint+=(s,e)=>{
   DrawScene(e.Graphics,parent);
   if(parent is Panel)Glass(e.Graphics,parent,new RectangleF(1,1,parent.Width-3,parent.Height-3),20,false,155);
   else if(parent is GroupBox)Glass(e.Graphics,parent,new RectangleF(1,1,parent.Width-3,parent.Height-3),18,false,180);
   else if(parent is Form && parent.Controls.Count<8)Glass(e.Graphics,parent,new RectangleF(14,14,parent.ClientSize.Width-28,parent.ClientSize.Height-28),22,true,165);
   foreach(Control c in parent.Controls){
    if(!OwnVisible(c))continue;
    if(c is TextBoxBase||c is ComboBox||c is NumericUpDown||c is DateTimePicker){RectangleF field=new RectangleF(c.Left-3,c.Top-4,c.Width+6,c.Height+8);Glass(e.Graphics,parent,field,10,false,238);continue;}
    RectangleF r=new RectangleF(c.Left,c.Top,c.Width,c.Height);
    if(c is Button){if(!IsPressed((Button)c))Shadow(e.Graphics,r,Math.Max(2,(c.Height-1)/2f));continue;}
    if(c is Panel||c is GroupBox||c is DataGridView){r.Inflate(3,3);Glass(e.Graphics,parent,r,20,true,c is DataGridView?230:150);}
   }
  };
 }
}
"@
}
function Set-UiTheme($Window) {
 if (-not (Get-Command Initialize-WorkdayWindows -ErrorAction SilentlyContinue)) { . (Join-Path $PSScriptRoot 'session.ps1') }
 Initialize-WorkdayWindows;Set-WorkdayTaskbarWindow $Window
 $iconPath=Join-Path $PSScriptRoot 'attendance.ico';if(Test-Path -LiteralPath $iconPath){$Window.Icon=New-Object Drawing.Icon($iconPath)}
 $script:UiBackground=[Drawing.ColorTranslator]::FromHtml('#F3F5FB');$script:UiInk=[Drawing.ColorTranslator]::FromHtml('#2E4058')
 $script:UiCyan=[Drawing.ColorTranslator]::FromHtml('#318C98');$script:UiMint=[Drawing.ColorTranslator]::FromHtml('#318C98');$script:UiOrange=[Drawing.ColorTranslator]::FromHtml('#318C98')
 $Window.BackColor=$script:UiBackground;$Window.ForeColor=$script:UiInk
 function Apply-SoftControls($parent){
  [WorkdaySoftTheme]::Container($parent)
  foreach($control in $parent.Controls){
   if($control -is [Windows.Forms.Button]){
    $primary=$control.Text -match '조회|저장|내보내기|신청|정리|작성|시작|설치'
    $control.BackColor=if($primary){$script:UiCyan}else{$script:UiBackground};$control.ForeColor=if($primary){[Drawing.Color]::White}else{$script:UiInk}
    $control.Font=New-Object Drawing.Font('Malgun Gothic',$(if($control.Width -lt 80){9}else{10}),[Drawing.FontStyle]::Bold);$control.Cursor=[Windows.Forms.Cursors]::Hand
    [WorkdaySoftTheme]::ApplyButton($control)
   }elseif($control -is [Windows.Forms.DataGridView]){
    $control.BackgroundColor=[Drawing.ColorTranslator]::FromHtml('#FBFCFF');$control.BorderStyle='None';$control.EnableHeadersVisualStyles=$false
    $control.ColumnHeadersDefaultCellStyle.BackColor=[Drawing.ColorTranslator]::FromHtml('#EEF0FA');$control.ColumnHeadersDefaultCellStyle.ForeColor=$script:UiInk
    $control.ColumnHeadersDefaultCellStyle.SelectionBackColor=[Drawing.ColorTranslator]::FromHtml('#C3D3DF');$control.ColumnHeadersDefaultCellStyle.SelectionForeColor=$script:UiInk
    $control.ColumnHeadersDefaultCellStyle.Alignment='MiddleCenter';$control.ColumnHeadersDefaultCellStyle.WrapMode='False';$control.DefaultCellStyle.Alignment='MiddleCenter';$control.DefaultCellStyle.WrapMode='False';
    foreach($column in $control.Columns){$column.HeaderText=($column.HeaderText -replace '\s+',' ').Trim();$column.HeaderCell.Style.Alignment='MiddleCenter';$column.DefaultCellStyle.Alignment='MiddleCenter';$width=[Windows.Forms.TextRenderer]::MeasureText($column.HeaderText,$control.Font).Width+22;$column.MinimumWidth=[Math]::Max($column.MinimumWidth,$width)}
    $control.Add_EditingControlShowing({param($sender,$args) if($args.Control -is [Windows.Forms.ComboBox]){[WorkdaySoftTheme]::Input($args.Control)}})
    $control.ColumnHeadersHeight=42;$control.DefaultCellStyle.BackColor=[Drawing.ColorTranslator]::FromHtml('#FFFFFF');$control.DefaultCellStyle.ForeColor=$script:UiInk
    $control.DefaultCellStyle.SelectionBackColor=[Drawing.ColorTranslator]::FromHtml('#C8DAE4');$control.DefaultCellStyle.SelectionForeColor=$script:UiInk
    $control.AlternatingRowsDefaultCellStyle.BackColor=[Drawing.ColorTranslator]::FromHtml('#F3F6FC');$control.GridColor=[Drawing.ColorTranslator]::FromHtml('#E5EAF3')
   }elseif($control -is [Windows.Forms.TextBoxBase] -or $control -is [Windows.Forms.ComboBox] -or $control -is [Windows.Forms.NumericUpDown] -or $control -is [Windows.Forms.DateTimePicker]){
    $control.BackColor=[Drawing.ColorTranslator]::FromHtml('#FBFCFE');$control.ForeColor=$script:UiInk
    if($control -is [Windows.Forms.TextBoxBase]){$control.BorderStyle='None';if($control -is [Windows.Forms.TextBox] -and -not $control.Multiline){$control.TextAlign='Center'}}
    if($control -is [Windows.Forms.ComboBox]){$control.FlatStyle='Flat';[WorkdaySoftTheme]::Input($control)}
    if($control -is [Windows.Forms.NumericUpDown]){$control.BorderStyle='None';$control.TextAlign='Center';[WorkdaySoftTheme]::Input($control)}
    if($control -is [Windows.Forms.DateTimePicker]){[WorkdaySoftTheme]::Input($control)}
   }elseif($control -is [Windows.Forms.Label]){
    if($control.BackColor.GetBrightness() -lt .5 -or $control.BackColor -eq [Drawing.Color]::White){$control.BackColor=[Drawing.Color]::Transparent;$control.ForeColor=$script:UiInk}
    if($parent -is [Windows.Forms.Panel]){$control.ForeColor=$script:UiInk};$control.BackColor=[Drawing.Color]::Transparent
   }elseif($control -is [Windows.Forms.Panel] -or $control -is [Windows.Forms.GroupBox]){
    $control.BackColor=$script:UiBackground;$control.ForeColor=$script:UiInk;if($control -is [Windows.Forms.GroupBox]){[WorkdaySoftTheme]::Group($control)};Apply-SoftControls $control
   }elseif($control -is [Windows.Forms.CheckBox]){$control.BackColor=[Drawing.Color]::Transparent;$control.ForeColor=$script:UiInk}
  }
 }
 Apply-SoftControls $Window
}
