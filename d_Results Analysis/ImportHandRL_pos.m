function HandRL_pos = ImportHandRL_pos(filename)
%IMPORTFILE 텍스트 파일의 숫자형 데이터를 행렬로 가져옵니다.
%   SUB115101U1APP2BODYKINEMATICSPOSGLOBAL = IMPORTFILE(FILENAME)
%   디폴트 선택 항목의 텍스트 파일 FILENAME에서 데이터를 읽습니다.
%
%   SUB115101U1APP2BODYKINEMATICSPOSGLOBAL = IMPORTFILE(FILENAME, STARTROW, ENDROW)
%   텍스트 파일 FILENAME의 STARTROW 행에서 ENDROW 행까지 데이터를 읽습니다.
%
% Example:
%   SUB115101U1APP2BodyKinematicsposglobal = importfile('SUB1_15_10_1_U1_APP2_BodyKinematics_pos_global.sto', 15, 177);
%
%    TEXTSCAN도 참조하십시오.

% MATLAB에서 다음 날짜에 자동 생성됨: 2024/02/28 14:58:17

%% 변수를 초기화합니다.
if nargin<=2
    startRow = 15;
    endRow = inf;
end

%% 데이터 열을 텍스트로 읽음:
% 자세한 내용은 도움말 문서에서 TEXTSCAN을 참조하십시오.
formatSpec = '%*2465s%17s%17s%17s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17*s%*17s%17s%17s%17s%[^\n\r]';

%% 텍스트 파일을 엽니다.
fileID = fopen(filename,'r');

%% 형식에 따라 데이터 열을 읽습니다.
% 이 호출은 이 코드를 생성하는 데 사용되는 파일의 구조체를 기반으로 합니다. 다른 파일에 대한 오류가 발생하는 경우 가져오기 툴에서 코드를 다시 생성하십시오.
textscan(fileID, '%[^\n\r]', startRow(1)-1, 'WhiteSpace', '', 'ReturnOnError', false);
dataArray = textscan(fileID, formatSpec, endRow(1)-startRow(1)+1, 'Delimiter', '', 'WhiteSpace', '', 'TextType', 'string', 'ReturnOnError', false, 'EndOfLine', '\r\n');
for block=2:length(startRow)
    frewind(fileID);
    textscan(fileID, '%[^\n\r]', startRow(block)-1, 'WhiteSpace', '', 'ReturnOnError', false);
    dataArrayBlock = textscan(fileID, formatSpec, endRow(block)-startRow(block)+1, 'Delimiter', '', 'WhiteSpace', '', 'TextType', 'string', 'ReturnOnError', false, 'EndOfLine', '\r\n');
    for col=1:length(dataArray)
        dataArray{col} = [dataArray{col};dataArrayBlock{col}];
    end
end

%% 텍스트 파일을 닫습니다.
fclose(fileID);

%% 숫자형 텍스트가 있는 열의 내용을 숫자로 변환합니다.
% 숫자형이 아닌 텍스트를 NaN으로 바꿉니다.
raw = repmat({''},length(dataArray{1}),length(dataArray)-1);
for col=1:length(dataArray)-1
    raw(1:length(dataArray{col}),col) = mat2cell(dataArray{col}, ones(length(dataArray{col}), 1));
end
numericData = NaN(size(dataArray{1},1),size(dataArray,2));

for col=[1,2,3,4,5,6]
    % 입력 셀형 배열의 텍스트를 숫자로 변환합니다. 숫자형이 아닌 텍스트를 NaN으로 바꿨습니다.
    rawData = dataArray{col};
    for row=1:size(rawData, 1)
        % 숫자형이 아닌 접두사 및 접미사를 검색하고 제거하는 정규 표현식을 만듭니다.
        regexstr = '(?<prefix>.*?)(?<numbers>([-]*(\d+[\,]*)+[\.]{0,1}\d*[eEdD]{0,1}[-+]*\d*[i]{0,1})|([-]*(\d+[\,]*)*[\.]{1,1}\d+[eEdD]{0,1}[-+]*\d*[i]{0,1}))(?<suffix>.*)';
        try
            result = regexp(rawData(row), regexstr, 'names');
            numbers = result.numbers;

            % 천 단위가 아닌 위치에서 쉼표를 검색했습니다.
            invalidThousandsSeparator = false;
            if numbers.contains(',')
                thousandsRegExp = '^[-/+]*\d+?(\,\d{3})*\.{0,1}\d*$';
                if isempty(regexp(numbers, thousandsRegExp, 'once'))
                    numbers = NaN;
                    invalidThousandsSeparator = true;
                end
            end
            % 숫자형 텍스트를 숫자로 변환합니다.
            if ~invalidThousandsSeparator
                numbers = textscan(char(strrep(numbers, ',', '')), '%f');
                numericData(row, col) = numbers{1};
                raw{row, col} = numbers{1};
            end
        catch
            raw{row, col} = rawData{row};
        end
    end
end


%% 숫자형이 아닌 셀이 있는 행 제외
I = ~all(cellfun(@(x) (isnumeric(x) || islogical(x)) && ~isnan(x),raw),2); % 숫자형이 아닌 셀이 있는 행 찾기
raw(I,:) = [];

%% 출력 변수 만들기
HandRL_pos = cell2mat(raw);
