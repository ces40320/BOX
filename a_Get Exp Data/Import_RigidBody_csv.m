function RigidBody = Import_RigidBody_csv(filename)
%IMPORTFILE 텍스트 파일에서 데이터 가져오기
%  RigidBody = Import_RigidBody_csv(FILENAME)은 디폴트 선택 사항에 따라 텍스트 파일 FILENAME에서
%  데이터를 읽습니다.  숫자형 데이터를 반환합니다.
% 
%  예:
%  RigidBody = Import_RigidBody_csv("E:\Dropbox\SEL\BOX\Experiment\240124_SUB1_PJH\RigidBody\BOX_15_10_trial1.csv");
%
%  RigidBody = Import_RigidBody_csv(FILE, DATALINES)는 텍스트 파일 FILENAME의 데이터를
%  지정된 행 간격으로 읽습니다. DATALINES를 양의 정수 스칼라로 지정하거나 양의 정수 스칼라로 구성된 N×2
%  배열(인접하지 않은 행 간격인 경우)로 지정하십시오.
%
%  예:
%  RigidBody = Import_RigidBody_csv("E:\Dropbox\SEL\BOX\Experiment\240124_SUB1_PJH\RigidBody\BOX_15_10_trial1.csv", [8, Inf]);
%
%  READTABLE도 참조하십시오.
%
% MATLAB에서 2024-02-01 20:29:55에 자동 생성됨

%% 입력 처리

% dataLines를 지정하지 않는 경우 디폴트 값을 정의하십시오.
if nargin < 2
    dataLines = [9, Inf];
end

%% 가져오기 옵션을 설정하고 데이터 가져오기
opts = delimitedTextImportOptions("NumVariables", 41);

% 범위 및 구분 기호 지정
opts.DataLines = dataLines;
opts.Delimiter = ",";

% 열 이름과 유형 지정
opts.VariableNames = ["Var1", "Var2", "RigidBody", "RigidBody_1", "RigidBody_2", "RigidBody_3", "RigidBody_4", "RigidBody_5", "Var9", "Var10", "Var11", "Var12", "Var13", "Var14", "Var15", "Var16", "Var17", "Var18", "Var19", "Var20", "Var21", "Var22", "Var23", "Var24", "Var25", "Var26", "Var27", "Var28", "Var29", "Var30", "Var31", "Var32", "Var33", "Var34", "Var35", "Var36", "Var37", "Var38", "Var39", "Var40", "Var41"];
opts.SelectedVariableNames = ["RigidBody", "RigidBody_1", "RigidBody_2", "RigidBody_3", "RigidBody_4", "RigidBody_5"];
opts.VariableTypes = ["string", "string", "double", "double", "double", "double", "double", "double", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string", "string"];

% 파일 수준 속성 지정
opts.ExtraColumnsRule = "ignore";
opts.EmptyLineRule = "read";

% 변수 속성 지정
opts = setvaropts(opts, ["Var1", "Var2", "Var9", "Var10", "Var11", "Var12", "Var13", "Var14", "Var15", "Var16", "Var17", "Var18", "Var19", "Var20", "Var21", "Var22", "Var23", "Var24", "Var25", "Var26", "Var27", "Var28", "Var29", "Var30", "Var31", "Var32", "Var33", "Var34", "Var35", "Var36", "Var37", "Var38", "Var39", "Var40", "Var41"], "WhitespaceRule", "preserve");
opts = setvaropts(opts, ["Var1", "Var2", "Var9", "Var10", "Var11", "Var12", "Var13", "Var14", "Var15", "Var16", "Var17", "Var18", "Var19", "Var20", "Var21", "Var22", "Var23", "Var24", "Var25", "Var26", "Var27", "Var28", "Var29", "Var30", "Var31", "Var32", "Var33", "Var34", "Var35", "Var36", "Var37", "Var38", "Var39", "Var40", "Var41"], "EmptyFieldRule", "auto");

% 데이터 가져오기
trial = readtable(filename, opts);

%% 출력 유형으로 변환
trial = table2array(trial);

RigidBody.RotX = trial(:,1);
RigidBody.RotY = trial(:,2);
RigidBody.RotZ = trial(:,3);
RigidBody.X = trial(:,4);
RigidBody.Y = trial(:,5);
RigidBody.Z = trial(:,6);

end