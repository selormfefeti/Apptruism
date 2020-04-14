using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace IRSData
{
    public class FormType990
    {

        private List<string> mPersonNm;
        private List<string> mTitleTxt;
        private List<string> mOfficerInd;
        private List<string> mIndividualTrusteeOrDirectorInd;
        private List<string> mReportableCompFromOrgAmt;
        private List<string> mReportableCompFromRltdOrgAmt;
        private List<string> mOtherCompensationAmt;
        private List<string> mTotalReportableCompFromOrgAmt;
        private List<string> mIndivRcvdGreaterThan100KCnt;
        private List<string> mTotalCompGreaterThan150KInd;

        [XPathAttibute(@"/Return/ReturnHeader/Filer/BusinessName/")]
        public string BusinessNameLine1Txt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string WebsiteAddressTxt { get; set; }

        [XPathAttibute(@"/Return/ReturnHeader/Filer/USAddress/")]
        public string ZIPCd { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string ActivityOrMissionDesc { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PYContributionsGrantsAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYContributionsGrantsAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PYTotalRevenueAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYTotalRevenueAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PYTotalExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYTotalExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PYRevenuesLessExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYRevenuesLessExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalAssetsBOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalAssetsEOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalLiabilitiesBOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalLiabilitiesEOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string NetAssetsOrFundBalancesBOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string NetAssetsOrFundBalancesEOYAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string MembershipDuesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalProgramServiceExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PYProgramServiceRevenueAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYProgramServiceRevenueAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalProgramServiceRevenueAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYTotalFundraisingExpenseAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string FundraisingDirectExpensesAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string VotingMembersGoverningBodyCnt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string VotingMembersIndependentCnt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string GoverningBodyVotingMembersCnt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string IndependentVotingMemberCnt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PoliticalCampaignActyInd { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string LobbyingActivitiesInd { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string FamilyOrBusinessRlnInd { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/CompCurrentOfcrDirectorsGrp/")]
        public string TotalAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalEmployeeCnt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string TotalVolunteersCnt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string PYSalariesCompEmpBnftPaidAmt { get; set; }

        [XPathAttibute(@"/Return/ReturnData/IRS990/")]
        public string CYSalariesCompEmpBnftPaidAmt { get; set; }

        //(“/Return/ReturnData/IRS990/Form990PartVIISectionAGr/
        //Form990PartVIISectionAGrp(!!!!REPEATER!!!!)
        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string PersonNm
        {
            get
            {
                return AggregateRepeaters(mPersonNm);
            }
            set
            {
                mPersonNm = SetRepeaterValue(mPersonNm, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string TitleTxt
        {
            get
            {
                return AggregateRepeaters(mTitleTxt);
            }
            set
            {
                mTitleTxt = SetRepeaterValue(mTitleTxt, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string IndividualTrusteeOrDirectorInd
        {
            get
            {
                return AggregateRepeaters(mIndividualTrusteeOrDirectorInd);
            }
            set
            {
                mIndividualTrusteeOrDirectorInd = SetRepeaterValue(mIndividualTrusteeOrDirectorInd, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string OfficerInd
        {
            get
            {
                return AggregateRepeaters(mOfficerInd);
            }
            set
            {
                mOfficerInd = SetRepeaterValue(mOfficerInd, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string ReportableCompFromOrgAmt
        {
            get
            {
                return AggregateRepeaters(mReportableCompFromOrgAmt);
            }
            set
            {
                mReportableCompFromOrgAmt = SetRepeaterValue(mReportableCompFromOrgAmt, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string ReportableCompFromRltdOrgAmt
        {
            get
            {
                return AggregateRepeaters(mReportableCompFromRltdOrgAmt);
            }
            set
            {
                mReportableCompFromRltdOrgAmt = SetRepeaterValue(mReportableCompFromRltdOrgAmt, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string OtherCompensationAmt
        {
            get
            {
                return AggregateRepeaters(mOtherCompensationAmt);
            }
            set
            {
                mOtherCompensationAmt = SetRepeaterValue(mOtherCompensationAmt, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string TotalReportableCompFromOrgAmt
        {
            get
            {
                return AggregateRepeaters(mTotalReportableCompFromOrgAmt);
            }
            set
            {
                mTotalReportableCompFromOrgAmt = SetRepeaterValue(mTotalReportableCompFromOrgAmt, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string IndivRcvdGreaterThan100KCnt
        {
            get
            {
                return AggregateRepeaters(mIndivRcvdGreaterThan100KCnt);
            }
            set
            {
                mIndivRcvdGreaterThan100KCnt = SetRepeaterValue(mIndivRcvdGreaterThan100KCnt, value);
            }
        }

        [XPathAttibute(@"/Return/ReturnData/IRS990/Form990PartVIISectionAGrp/", true)]
        public string TotalCompGreaterThan150KInd
        {
            get
            {
                return AggregateRepeaters(mTotalCompGreaterThan150KInd);
            }
            set
            {
                mTotalCompGreaterThan150KInd = SetRepeaterValue(mTotalCompGreaterThan150KInd, value);
            }
        }

        internal string AggregateRepeaters(List<string> aggRep, string seperater = ";")
        {
            string rtn = string.Empty;
            if (aggRep != null)
            {
                rtn = aggRep.Aggregate((a, b) => a + seperater + " " + b);
            }

            return rtn;
        }

        internal List<string> SetRepeaterValue(List<string> rep, string value)
        {
            if (rep == null)
            {
                rep = new List<string>();
            }

            rep.Add(value);

            return rep;
        }
    }
}
